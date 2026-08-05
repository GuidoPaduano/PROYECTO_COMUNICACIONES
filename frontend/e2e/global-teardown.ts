import { execFileSync } from "node:child_process"
import path from "node:path"

function resolvePython(projectRoot: string): string {
  if (process.env.DJANGO_PYTHON) return process.env.DJANGO_PYTHON
  return process.platform === "win32"
    ? path.join(projectRoot, "venv", "Scripts", "python.exe")
    : path.join(projectRoot, "venv", "bin", "python")
}

export default async function globalTeardown() {
  const projectRoot = path.resolve(__dirname, "../..")
  const python = resolvePython(projectRoot)

  execFileSync(python, ["manage.py", "seed_qa_data", "--reset-passwords", "--reset-e2e-data"], {
    cwd: projectRoot,
    stdio: "inherit",
  })
}
