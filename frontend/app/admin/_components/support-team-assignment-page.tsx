"use client"

import Link from "next/link"
import EoeSchoolTeam from "./eoe-school-team"
import IntegrationStudentAssignmentPage from "./integration-student-assignment-page"

const teams = [
  { role: "EOE", label: "EOE", href: "/admin/colegio/eoe-integracion" },
  { role: "Integracion", label: "Integración", href: "/admin/colegio/eoe-integracion/integracion" },
] as const

export default function SupportTeamAssignmentPage({ role }: { role: "EOE" | "Integracion" }) {
  const navigation = (
        <nav aria-label="Equipo de acompañamiento" className="flex w-fit gap-1 rounded-xl border border-slate-200 bg-white p-1">
          {teams.map((team) => (
            <Link
              key={team.role}
              href={team.href}
              aria-current={role === team.role ? "page" : undefined}
              style={role === team.role ? { backgroundColor: "var(--school-primary, #0f1e46)", color: "#ffffff" } : undefined}
              className={`rounded-lg px-5 py-2 text-sm font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 ${role === team.role ? "text-white" : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"}`}
            >
              {team.label}
            </Link>
          ))}
        </nav>
  )
  if (role === "EOE") return <EoeSchoolTeam navigation={navigation} />
  return <IntegrationStudentAssignmentPage navigation={navigation} />
}
