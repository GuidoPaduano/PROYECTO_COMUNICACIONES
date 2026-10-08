import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import MessageReminder from "@/components/message-reminder"
import { authFetch } from "@/app/_lib/auth"
jest.mock("@/app/_lib/auth", () => ({ authFetch: jest.fn() }))
const request=authFetch as jest.Mock
beforeEach(()=>request.mockReset())

it("allows an immediate reminder and then starts cooldown",async()=>{
 request.mockResolvedValue({ok:true,json:async()=>({detail:"Recordatorio enviado.",ultimo_recordatorio_en:new Date().toISOString()})})
 render(<MessageReminder message={{id:7,leido:false}} />)
 expect(screen.getByRole('button',{name:'Enviar recordatorio'})).toBeEnabled()
 fireEvent.click(screen.getByRole('button',{name:'Enviar recordatorio'}))
 expect(await screen.findByRole('status')).toHaveTextContent('Recordatorio enviado')
 expect(screen.getByRole('button',{name:'Enviar recordatorio'})).toBeDisabled()
 expect(request).toHaveBeenCalledWith('/mensajes/7/recordatorio',expect.objectContaining({method:'POST',body:JSON.stringify({accion:'recordar'})}))
})
it("shows only an icon button for a read message",()=>{
 render(<MessageReminder message={{id:7,leido:true}} />)
 const button = screen.getByRole('button',{name:'Enviar recordatorio'})
 expect(button).toBeEnabled()
 expect(button).toHaveTextContent('')
 expect(screen.getAllByRole('button')).toHaveLength(1)
 expect(screen.queryByText('Leído, sin respuesta')).not.toBeInTheDocument()
})
it("does not offer reminders on answered messages",()=>{
 render(<MessageReminder message={{id:7,recordatorio_respondido:true}} />)
 expect(screen.queryByRole('button',{name:'Enviar recordatorio'})).not.toBeInTheDocument()
})
it("shows server errors and lets the sender retry",async()=>{
 request.mockRejectedValue(new Error('No se pudo conectar'))
 render(<MessageReminder message={{id:7}} />)
 fireEvent.click(screen.getByRole('button',{name:'Enviar recordatorio'}))
 expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo conectar')
 await waitFor(()=>expect(screen.getByRole('button',{name:'Enviar recordatorio'})).toBeEnabled())
})
