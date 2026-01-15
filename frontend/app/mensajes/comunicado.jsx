"use client"

import Link from "next/link"
import { useState } from "react"
import { useAuthGuard } from "../_lib/auth"
import { Bell, Mail, User as UserIcon, ChevronDown, ChevronLeft, Megaphone } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import ComposeComunicadoFamilia from "./_compose-comunicado-familia"

export default function ComunicadoFamiliasPage() {
  useAuthGuard()
  const [open, setOpen] = useState(false)

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-25 to-white">
      {/* Topbar */}
      <div className="bg-blue-600 text-white px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-semibold flex items-center gap-2">
              <Megaphone className="h-6 w-6" />
              Comunicados a Familias
            </h1>
          </div>

          <div className="flex items-center gap-2">
            <Link href="/dashboard">
              <Button variant="ghost" className="text-white hover:bg-blue-700 gap-2">
                <ChevronLeft className="h-4 w-4" />
                Volver al panel
              </Button>
            </Link>
            <Button variant="ghost" size="icon" className="text-white hover:bg-blue-700">
              <Bell className="h-5 w-5" />
            </Button>
            <Button variant="ghost" size="icon" className="text-white hover:bg-blue-700">
              <Mail className="h-5 w-5" />
            </Button>
            <Button variant="ghost" className="text-white hover:bg-blue-700 gap-2">
              <UserIcon className="h-5 w-5" />
              <ChevronDown className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>

      {/* Contenido */}
      <div className="max-w-5xl mx-auto px-4 py-8">
        <Card className="shadow-sm border-0 bg-white/80 backdrop-blur-sm">
          <CardContent className="p-6">
            <p className="text-gray-700 mb-4">
              Enviá comunicados a las familias seleccionando primero el curso y luego el padre/madre/tutor.
            </p>
            <Button onClick={() => setOpen(true)}>Nuevo comunicado</Button>
          </CardContent>
        </Card>
      </div>

      {/* Modal */}
      <ComposeComunicadoFamilia open={open} onOpenChange={setOpen} />
    </div>
  )
}
