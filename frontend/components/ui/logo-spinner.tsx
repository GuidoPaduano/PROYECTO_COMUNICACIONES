import Image from "next/image"

interface LogoSpinnerProps {
  logoUrl?: string
  size?: number
  label?: string
}

const DEFAULT_LOGO = "/imagenes/Logo Color.png"

export default function LogoSpinner({
  logoUrl,
  size = 96,
  label = "Cargando...",
}: LogoSpinnerProps) {
  const src = logoUrl || DEFAULT_LOGO

  return (
    <div className="flex flex-col items-center justify-center gap-4">
      <div className="logo-spin-wrap">
        <Image
          src={src}
          alt={label}
          width={size}
          height={size}
          unoptimized
          className="logo-spin"
          style={{ width: size, height: "auto" }}
        />
      </div>
      {label && (
        <p className="text-sm text-slate-500 animate-pulse">{label}</p>
      )}
    </div>
  )
}
