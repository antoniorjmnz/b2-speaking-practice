import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const workspace = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const candidates =
  process.platform === "win32"
    ? [resolve(workspace, "apps/api/.venv/Scripts/python.exe")]
    : [resolve(workspace, "apps/api/.venv/bin/python")];
const python =
  candidates.find((candidate) => existsSync(candidate)) ??
  process.env.PYTHON ??
  (process.platform === "win32" ? "python" : "python3");
const result = spawnSync(python, process.argv.slice(2), {
  cwd: workspace,
  stdio: "inherit",
  shell: false,
});

if (result.error) {
  console.error(`No se pudo ejecutar Python: ${result.error.message}`);
  process.exit(1);
}
process.exit(result.status ?? 1);
