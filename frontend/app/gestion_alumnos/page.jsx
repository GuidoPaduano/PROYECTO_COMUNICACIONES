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
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-25 to-white flex items-center justify-center">
      <div className="text-sm text-gray-600">Cargando…</div>
    </div>
  )
}
