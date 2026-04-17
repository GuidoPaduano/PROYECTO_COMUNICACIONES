"use client"

import dynamic from "next/dynamic"
import { useState } from "react"
import { useAuthGuard } from "../_lib/auth"
import { Megaphone } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"

const ComposeComunicadoFamilia = dynamic(() => import("./_compose-comunicado-familia"), {
  loading: () => null,
})

export default function ComunicadoFamiliasPage() {
  useAuthGuard()
  const [open, setOpen] = useState(false)

  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="space-y-3">
          <div className="flex items-center gap-2 text-slate-900 font-semibold">
            <div className="h-10 w-10 rounded-xl flex items-center justify-center school-primary-soft-icon">
              <Megaphone className="h-5 w-5" />
            </div>
            <div>
              <div className="text-lg">Comunicados a familias</div>
              <div className="text-sm text-slate-500">
                Envía comunicados seleccionando primero el curso y luego el destinatario.
              </div>
            </div>
          </div>
          <Button onClick={() => setOpen(true)}>Nuevo comunicado</Button>
        </CardContent>
      </Card>

      {open ? <ComposeComunicadoFamilia open={open} onOpenChange={setOpen} /> : null}
    </div>
  )
}
