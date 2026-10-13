import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import IntegrationStudentAssignmentPage from "@/app/admin/_components/integration-student-assignment-page"
import { authFetch } from "@/app/_lib/auth"

jest.mock("@/app/_lib/auth", () => ({
  authFetch: jest.fn(), useAuthGuard: jest.fn(),
  useSessionContext: () => ({ username:'admin', isSuperuser:true, groups:[], school:{id:1,slug:'school'} }),
}))
const request = authFetch as jest.Mock
const payload = {
  alumnos:[{id:1,nombre:'Ana',apellido:'Acosta',curso:'1A',legajo:'A1',maestra_ids:[]},{id:2,nombre:'Beto',apellido:'Bravo',curso:'1A',legajo:'A2',maestra_ids:[8]}],
  maestras:[{id:7,nombre:'Maestra A',email:'a@example.com',disponible:true},{id:8,nombre:'Maestra B',email:'b@example.com',disponible:true}],
}
beforeEach(()=>request.mockReset())

it('saves assignments by student and keeps drafts separate when switching students',async()=>{
  request.mockImplementation(async (_url, options) => ({ok:true,json:async()=>options?.method==='PATCH' ? {maestra_ids:[7]} : payload}))
  render(<IntegrationStudentAssignmentPage navigation={<div>Equipos</div>} />)
  await screen.findByLabelText('Alumno')
  expect(screen.queryByLabelText('Curso',{exact:true})).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('checkbox',{name:/Maestra A/}))
  fireEvent.change(screen.getByLabelText('Alumno'),{target:{value:'2'}})
  expect(screen.getByRole('checkbox',{name:/Maestra A/})).not.toBeChecked()
  expect(screen.getByRole('checkbox',{name:/Maestra B/})).toBeChecked()
  fireEvent.change(screen.getByLabelText('Alumno'),{target:{value:'1'}})
  expect(screen.getByRole('checkbox',{name:/Maestra A/})).toBeChecked()
  expect(screen.getByRole('checkbox',{name:/Maestra B/})).not.toBeChecked()
  fireEvent.click(screen.getByRole('button',{name:'Guardar asignación'}))
  expect(await screen.findByRole('status')).toHaveTextContent('Asignación de Acosta, Ana guardada')
  expect(request).toHaveBeenLastCalledWith('/admin/integracion/alumnos/1',expect.objectContaining({method:'PATCH',body:JSON.stringify({maestra_ids:[7]})}))
})

it('does not offer saving when loading fails',async()=>{
  request.mockResolvedValue({ok:false,json:async()=>({detail:'No autorizado'})})
  render(<IntegrationStudentAssignmentPage navigation={null} />)
  expect(await screen.findByRole('alert')).toHaveTextContent('No autorizado')
  expect(screen.queryByRole('button',{name:'Guardar asignación'})).not.toBeInTheDocument()
})

it('preserves the selected teachers after a failed save so it can be retried',async()=>{
  request.mockImplementation(async (_url, options) => options?.method==='PATCH' ? {ok:false,json:async()=>({detail:'No se pudo guardar'})} : {ok:true,json:async()=>payload})
  render(<IntegrationStudentAssignmentPage navigation={null} />)
  await screen.findByLabelText('Alumno')
  fireEvent.click(screen.getByRole('checkbox',{name:/Maestra A/}))
  fireEvent.click(screen.getByRole('button',{name:'Guardar asignación'}))
  expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo guardar')
  expect(screen.getByRole('checkbox',{name:/Maestra A/})).toBeChecked()
  await waitFor(()=>expect(screen.getByRole('button',{name:'Guardar asignación'})).toBeEnabled())
})
