import { execFileSync } from "node:child_process"
import path from "node:path"

export default async function globalTeardown() {
  const projectRoot = path.resolve(__dirname, "../..")
  const python = path.join(projectRoot, "venv", "Scripts", "python.exe")

  execFileSync(python, ["manage.py", "seed_qa_data", "--reset-passwords", "--reset-e2e-data"], {
    cwd: projectRoot,
    stdio: "inherit",
  })
}
