import StaffCourseAssignmentPage from "../../_components/staff-course-assignment-page"

export default function AdminColegioAsignacionPreceptoresPage() {
  return (
    <StaffCourseAssignmentPage
      role="Preceptores"
      title="Asignacion a preceptores"
      description="Asigna preceptores a los cursos del colegio activo desde una pantalla propia del admin de colegio."
      backHref="/admin/colegio"
      backLabel="Volver a admin colegio"
    />
  )
}
