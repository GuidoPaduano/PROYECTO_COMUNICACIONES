"use client"

import Link from "next/link"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Mail } from "lucide-react"
import { PropsWithChildren, ReactNode } from "react"

type Props = {
  /** Ruta a la vista que abre el modal o la pantalla de mensajes. Si preferís abrir inline, no pases href y usá onClick. */
  href?: string
  /** Handler opcional para abrir el modal directamente en la misma pantalla. Si se define, no se usa el Link. */
  onClick?: () => void
}

function Wrapper({
  children,
  href,
  onClick,
}: PropsWithChildren<{ href?: string; onClick?: () => void }>) {
  if (onClick) {
    return (
      <button onClick={onClick} className="w-full text-left">
        {children}
      </button>
    )
  }
  if (href && href !== "#") {
    return (
      <Link href={href} className="block w-full">
        {children}
      </Link>
    )
  }
  return <div className="w-full">{children}</div>
}

/**
 * Tarjeta para el panel de preceptores.
 * Título: "Enviar mensajes"
 * Subtítulo: "Envía mensajes a alumnos, cursos o padres"
 */
export default function EnviarMensajesCard({ href = "#", onClick }: Props) {
  let actionEl: ReactNode = null
  if (onClick) {
    actionEl = (
      <Button onClick={onClick}>
        Crear
      </Button>
    )
  } else if (href && href !== "#") {
    actionEl = (
      <Link href={href}>
        <Button>Crear</Button>
      </Link>
    )
  } else {
    actionEl = (
      <Button disabled>
        Crear
      </Button>
    )
  }

  return (
    <Card className="transition-shadow hover:shadow-md">
      <CardContent className="flex items-center gap-4 p-4">
        <div className="flex h-10 w-10 items-center justify-center rounded-full border">
          <Mail className="h-5 w-5" />
        </div>

        <div className="min-w-0 flex-1">
          <Wrapper href={href} onClick={onClick}>
            <div>
              <div className="truncate font-semibold">Enviar mensajes</div>
              <div className="text-sm text-muted-foreground">
                Envía mensajes a alumnos, cursos o padres
              </div>
            </div>
          </Wrapper>
        </div>

        <div className="shrink-0">
          {actionEl}
        </div>
      </CardContent>
    </Card>
  )
}
