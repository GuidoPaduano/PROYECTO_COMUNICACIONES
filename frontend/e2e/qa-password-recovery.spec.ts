import { execFileSync } from "node:child_process"
import path from "node:path"

import { expect, test } from "@playwright/test"

test.describe("QA password recovery UI", () => {
  test.skip(({ browserName }) => browserName === "webkit", "WebKit bloqueado en el runner Windows local")

  test("forgot password muestra respuesta generica exitosa", async ({ page }) => {
    await page.route("**/api/auth/password-reset/", async (route) => {
      const request = route.request()
      expect(request.method()).toBe("POST")
      expect(await request.postDataJSON()).toEqual({ email: "familia@test.local" })
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Si el correo existe, se enviara un enlace." }),
      })
    })

    await page.goto("/forgot-password?school=qa-local")
    await page.getByLabel("Email").fill("familia@test.local")
    await page.getByRole("button", { name: "Enviar link" }).click()
    await expect(page.getByText("Si el correo existe, se enviara un enlace.")).toBeVisible()
  })

  test("forgot password presenta el error devuelto por la API", async ({ page }) => {
    await page.route("**/api/auth/password-reset/", async (route) => {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Servicio de correo no disponible." }),
      })
    })

    await page.goto("/forgot-password?school=qa-local")
    await page.getByLabel("Email").fill("familia@test.local")
    await page.getByRole("button", { name: "Enviar link" }).click()
    await expect(page.getByText("Servicio de correo no disponible.")).toBeVisible()
  })

  test("reset password valida link incompleto y passwords diferentes sin llamar a la API", async ({
    page,
  }) => {
    let requests = 0
    await page.route("**/api/auth/password-reset/confirm/", async (route) => {
      requests += 1
      await route.abort()
    })

    await page.goto("/reset-password?school=qa-local")
    await page.getByLabel(/contrase.a nueva/i).fill("NuevaClave123!")
    await page.getByLabel(/repetir contrase.a/i).fill("NuevaClave123!")
    await page.getByRole("button", { name: /actualizar contrase.a/i }).click()
    await expect(page.getByText(/link es inv.lido o est. incompleto/i)).toBeVisible()

    await page.goto("/reset-password?school=qa-local&uid=dWlk&token=token-prueba")
    await page.getByLabel(/contrase.a nueva/i).fill("NuevaClave123!")
    await page.getByLabel(/repetir contrase.a/i).fill("Distinta123!")
    await page.getByRole("button", { name: /actualizar contrase.a/i }).click()
    await expect(page.getByText(/contrase.as no coinciden/i)).toBeVisible()
    expect(requests).toBe(0)
  })

  test("reset password envia uid, token y password y muestra confirmacion", async ({ page }) => {
    await page.route("**/api/auth/password-reset/confirm/", async (route) => {
      const request = route.request()
      expect(request.method()).toBe("POST")
      expect(await request.postDataJSON()).toEqual({
        uid: "dWlk",
        token: "token-prueba",
        password: "NuevaClave123!",
      })
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Password actualizado correctamente." }),
      })
    })

    await page.goto("/reset-password?school=qa-local&uid=dWlk&token=token-prueba")
    await page.getByLabel(/contrase.a nueva/i).fill("NuevaClave123!")
    await page.getByLabel(/repetir contrase.a/i).fill("NuevaClave123!")
    await page.getByRole("button", { name: /actualizar contrase.a/i }).click()
    await expect(page.getByText("Password actualizado correctamente.")).toBeVisible()
  })

  test("token real cambia el password, permite login y no puede reutilizarse", async ({
    page,
    browserName,
  }) => {
    test.skip(browserName !== "chromium", "La integracion real se ejecuta una vez en Chromium")

    const username = `qa_reset_${Date.now()}`
    const oldPassword = "ClaveTemporal123!"
    const newPassword = "ClaveNuevaSegura123!"
    const tokenData = createTemporaryResetUser(username, oldPassword)

    try {
      await page.goto(resetUrl(tokenData))
      await page.getByLabel(/contrase.a nueva/i).fill(newPassword)
      await page.getByLabel(/repetir contrase.a/i).fill(newPassword)
      await page.getByRole("button", { name: /actualizar contrase.a/i }).click()
      await expect(page.getByText(/contrase.a actualizada/i)).toBeVisible()

      await page.goto("/login?school=qa-local")
      await page.getByLabel(/usuario/i).fill(username)
      await page.getByLabel(/contrase/i).fill(newPassword)
      await page.getByRole("button", { name: /ingresar/i }).click()
      await expect(page).toHaveURL(/\/admin\/colegio/)

      await page.goto(resetUrl(tokenData))
      await page.getByLabel(/contrase.a nueva/i).fill("OtraClaveSegura123!")
      await page.getByLabel(/repetir contrase.a/i).fill("OtraClaveSegura123!")
      await page.getByRole("button", { name: /actualizar contrase.a/i }).click()
      await expect(page.getByText(/link inv.lido o expirado/i)).toBeVisible()
    } finally {
      deleteTemporaryUser(username)
    }
  })
})

function resetUrl(tokenData: { uid: string; token: string }) {
  return `/reset-password?school=qa-local&uid=${encodeURIComponent(tokenData.uid)}&token=${encodeURIComponent(tokenData.token)}`
}

function runDjangoShell(script: string) {
  const projectRoot = path.resolve(__dirname, "../..")
  const python = path.join(projectRoot, "venv", "Scripts", "python.exe")
  return execFileSync(python, ["manage.py", "shell", "-c", script], {
    cwd: projectRoot,
    encoding: "utf8",
  }).trim()
}

function createTemporaryResetUser(username: string, password: string) {
  const script = [
    "import json",
    "from django.contrib.auth import get_user_model",
    "from django.contrib.auth.tokens import default_token_generator",
    "from django.utils.http import urlsafe_base64_encode",
    `username=${JSON.stringify(username)}`,
    `password=${JSON.stringify(password)}`,
    "User=get_user_model()",
    "User.objects.filter(username=username).delete()",
    "user=User.objects.create_superuser(username=username, email=f'{username}@test.local', password=password)",
    "uid=urlsafe_base64_encode(str(user.pk).encode('utf-8'))",
    "token=default_token_generator.make_token(user)",
    "print(json.dumps({'uid': uid, 'token': token}))",
  ].join(";")
  return JSON.parse(runDjangoShell(script)) as { uid: string; token: string }
}

function deleteTemporaryUser(username: string) {
  const script = [
    "from django.contrib.auth import get_user_model",
    `username=${JSON.stringify(username)}`,
    "get_user_model().objects.filter(username=username).delete()",
  ].join(";")
  runDjangoShell(script)
}
