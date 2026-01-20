"use client"

import { useState } from "react"
import { useAuthGuard } from "../_lib/auth"
import { Megaphone } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import ComposeComunicadoFamilia from "./_compose-comunicado-familia"

export default function ComunicadoFamiliasPage() {
  useAuthGuard()
  const [open, setOpen] = useState(false)

  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="space-y-3">
          <div className="flex items-center gap-2 text-slate-900 font-semibold">
            <div className="h-10 w-10 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center">
              <Megaphone className="h-5 w-5" />
            </div>
            <div>
              <div className="text-lg">Comunicados a familias</div>
              <div className="text-sm text-slate-500">
                Envia comunicados seleccionando primero el curso y luego el destinatario.
              </div>
            </div>
          </div>
          <Button onClick={() => setOpen(true)}>Nuevo comunicado</Button>
        </CardContent>
      </Card>

      <ComposeComunicadoFamilia open={open} onOpenChange={setOpen} />
    </div>
  )
}
