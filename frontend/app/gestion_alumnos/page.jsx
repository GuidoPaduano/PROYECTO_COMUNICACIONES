"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { useAuthGuard } from "../_lib/auth"

export default function GestionAlumnosPage() {
  useAuthGuard()
  const router = useRouter()

  useEffect(() => {
    router.replace("/mis-cursos")
  }, [router])

  return (
    <div className="flex items-center justify-center">
      <div className="surface-card surface-card-pad text-sm text-gray-600">Cargando...</div>
    </div>
  )
}
