"use client"

import Link from "next/link"
import { ArrowRight } from "lucide-react"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

function ToolCard({ title, description, icon, href, external = false }) {
  const statusLabel = external ? "No disponible" : "Disponible"
  const statusClasses = external
    ? "bg-slate-100 text-slate-600 ring-slate-200"
    : "bg-emerald-50 text-emerald-700 ring-emerald-200"

  const body = (
    <Card className="h-full border-slate-200 transition hover:-translate-y-0.5 hover:shadow-md">
      <CardHeader className="space-y-4">
        <div className="flex items-center justify-between">
          <div
            className="inline-flex h-12 w-12 items-center justify-center rounded-2xl text-white shadow-sm"
            style={{ backgroundColor: "var(--school-primary)" }}
          >
            {icon}
          </div>
          <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${statusClasses}`}>
            {statusLabel}
          </span>
        </div>
        <div>
          <CardTitle className="text-slate-900">{title}</CardTitle>
          <CardDescription className="mt-2 text-sm leading-6 text-slate-600">
            {description}
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <div
          className="flex items-center text-sm font-medium"
          style={{ color: "var(--school-primary)" }}
        >
          <span>Abrir herramienta</span>
          <ArrowRight className="ml-2 h-4 w-4" />
        </div>
      </CardContent>
    </Card>
  )

  if (external) {
    return (
      <a href={href} target="_blank" rel="noreferrer" className="block h-full">
        {body}
      </a>
    )
  }

  return (
    <Link href={href} className="block h-full">
      {body}
    </Link>
  )
}

export function ToolSection({ title, description, tools }) {
  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
        {description ? (
          <p className="mt-1 text-sm leading-6 text-slate-600">{description}</p>
        ) : null}
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {tools.map((tool) => (
          <ToolCard key={tool.title} {...tool} />
        ))}
      </div>
    </section>
  )
}
