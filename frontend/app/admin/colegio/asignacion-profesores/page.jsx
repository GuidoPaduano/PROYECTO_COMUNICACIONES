import StaffCourseAssignmentPage from "../../_components/staff-course-assignment-page"

export default function AdminColegioAsignacionProfesoresPage() {
  return (
    <StaffCourseAssignmentPage
      role="Profesores"
      title="Asignacion a profesores"
      description="Asigna profesores a los cursos del colegio activo desde una pantalla propia del admin de colegio."
      backHref="/admin/colegio"
      backLabel="Volver a admin colegio"
    />
  )
}
