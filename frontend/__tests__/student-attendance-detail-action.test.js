const fs = require("fs")
const path = require("path")

describe("student attendance detail action", () => {
  it("no muestra el lapiz de detalle como boton deshabilitado", () => {
    const source = fs.readFileSync(
      path.join(__dirname, "../app/alumnos/[alumnoId]/page.tsx"),
      "utf8"
    )

    expect(source).not.toContain("disabled={!puedeDetalle}")
    expect(source).toContain("{puedeDetalle ? (")
  })
})
