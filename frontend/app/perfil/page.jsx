"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronDown,
  Mail,
  User,
  Edit3,
  Camera,
  Save,
  X,
  BadgeCheck,
  ArrowLeft,
  Inbox,
  Link2,
  KeyRound,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import SuccessMessage from "@/components/ui/success-message";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { INBOX_EVENT } from "../_lib/inbox";
import { NotificationBell } from "@/components/notification-bell";
import { authFetch, logout, useAuthGuard } from "../_lib/auth";

const LOGO_SRC = "/imagenes/Santa%20teresa%20logo.png"

export default function Profile() {
  useAuthGuard();

  const [isEditing, setIsEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [api, setApi] = useState(null);

  // Estado editable (sin teléfono)
  const [profileData, setProfileData] = useState({
    name: "",
    email: "",
    department: "",
    position: "",
  });

  // ===== Mensajería: badge de no leídos =====
  const [unreadCount, setUnreadCount] = useState(0);

  // ===== FIX: Vincular Alumno ↔ Usuario por legajo (id_alumno) =====
  const [legajo, setLegajo] = useState("");
  const [linking, setLinking] = useState(false);
  const [linkError, setLinkError] = useState("");
  const [linkOk, setLinkOk] = useState("");

  // ===== Cambiar contraseña =====
  const [showPasswordForm, setShowPasswordForm] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [pwdLoading, setPwdLoading] = useState(false);
  const [pwdError, setPwdError] = useState("");
  const [pwdOk, setPwdOk] = useState("");
  const [toast, setToast] = useState(null);
  const toastTimerRef = useRef(null);
  const logoutTimerRef = useRef(null);

  // Carga y refresco del contador de no leídos (igual que otras vistas)
  useEffect(() => {
    let alive = true;
    let timer = null;

    const loadUnread = async () => {
      try {
        // ✅ FIX: no usar "/api/..." con authFetch (evita /api/api/...)
        const res = await authFetch("/mensajes/unread_count/");
        if (!res.ok) return;

        const j = await res.json().catch(() => ({}));
        if (alive && typeof j?.count === "number") setUnreadCount(j.count);
      } catch {
        // silencio, se vuelve a intentar en el próximo tick
      }
    };

    loadUnread();
    timer = setInterval(loadUnread, 60000);

    const onInboxEvent = () => loadUnread();
    if (typeof window !== "undefined") {
      window.addEventListener(INBOX_EVENT, onInboxEvent);
    }

    return () => {
      alive = false;
      if (timer) clearInterval(timer);
      if (typeof window !== "undefined") {
        window.removeEventListener(INBOX_EVENT, onInboxEvent);
      }
    };
  }, []);

  // Fetch al perfil API (Django) usando authFetch
  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      try {
        setLoading(true);
        setError(null);

        const res = await authFetch("/perfil_api/", {
          headers: { Accept: "application/json" },
        });
        if (!res.ok) {
          let t = "";
          try {
            t = await res.text();
          } catch {}
          throw new Error(`Perfil API ${res.status} – ${t}`);
        }
        const data = await res.json();
        if (cancelled) return;
        setApi(data);

        const fullName =
          [data?.user?.first_name, data?.user?.last_name]
            .filter(Boolean)
            .join(" ") ||
          data?.user?.username ||
          "Usuario";

        setProfileData({
          name: fullName,
          email: data?.user?.email || "",
          position: data?.user?.rol || "",
          department: data?.curso_preceptor
            ? `Preceptor de: ${data.curso_preceptor}`
            : data?.alumno
            ? `Alumno: ${data.alumno.curso}`
            : data?.alumnos_del_padre && data.alumnos_del_padre.length
            ? "Responsable de alumnos"
            : "",
        });

        // ✅ Si el user ya tiene username con pinta de legajo, lo precargamos
        const u = data?.user?.username || "";
        if (!data?.alumno && u && u.length <= 32) {
          setLegajo(u);
        }
      } catch (e) {
        if (!cancelled) {
          setError((e && e.message) || "Error al cargar el perfil");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    run();
    return () => {
      cancelled = true;
    };
  }, []);

  const displayName = useMemo(
    () => profileData.name || "",
    [profileData.name]
  );

  const gruposTexto = useMemo(() => {
    const grupos =
      (api && api.user && (api.user.grupos || api.user.groups)) || [];
    const rol = api?.user?.is_superuser ? "superusuario" : api?.user?.rol;

    const base = grupos.length ? grupos.join(" · ") : "—";
    return rol && !grupos.includes(rol) ? `${base} · ${rol}` : base;
  }, [api]);

  const rolPrincipal = useMemo(() => {
    if (api?.user?.is_superuser) return "Administrador";
    const grupos = (api?.user?.grupos || api?.user?.groups || []).map((g) =>
      String(g || "").toLowerCase()
    );
    const rolRaw = String(api?.user?.rol || "").toLowerCase();
    const tokens = [rolRaw, ...grupos].filter(Boolean);
    if (tokens.some((t) => t.includes("preceptor"))) return "Preceptor";
    if (tokens.some((t) => t.includes("profesor"))) return "Profesor";
    if (tokens.some((t) => t.includes("padre"))) return "Padre";
    if (tokens.some((t) => t.includes("alumno"))) return "Alumno";
    if (api?.user?.rol) return String(api.user.rol);
    return "Usuario";
  }, [api]);

  const isPreceptor = useMemo(() => {
    const grupos = (api?.user?.grupos || api?.user?.groups || []).map((g) =>
      String(g || "").toLowerCase()
    );
    const rolRaw = String(api?.user?.rol || "").toLowerCase();
    return [rolRaw, ...grupos].some((t) => t.includes("preceptor"));
  }, [api]);

  const isAlumno = useMemo(() => {
    const grupos = (api?.user?.grupos || api?.user?.groups || []).map((g) =>
      String(g || "").toLowerCase()
    );
    const rolRaw = String(api?.user?.rol || "").toLowerCase();
    return [rolRaw, ...grupos].some((t) => t.includes("alumno"));
  }, [api]);

  const cursoAlumnoTexto = useMemo(() => {
    if (api?.alumno?.curso) return String(api.alumno.curso);
    const raw = String(profileData.department || "");
    return raw.replace(/^Alumno:\s*/i, "");
  }, [api, profileData.department]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const full = String(profileData.name || "").trim();
      const parts = full.split(/\s+/).filter(Boolean);
      const firstName = parts.shift() || "";
      const lastName = parts.join(" ");

      const res = await authFetch("/perfil_api/", {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          first_name: firstName,
          last_name: lastName,
          email: profileData.email || "",
        }),
      });

      const j = await res.json().catch(() => ({}));
      if (!res.ok) {
        showToast("error", j?.detail || "No se pudo guardar el perfil.");
        return;
      }

      showToast("success", "Perfil actualizado.");
      await refreshPerfilApi();
      setIsEditing(false);
    } catch {
      showToast("error", "No se pudo conectar con el servidor.");
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    setIsEditing(false);
    if (api) {
      const fullName =
        [api?.user?.first_name, api?.user?.last_name]
          .filter(Boolean)
          .join(" ") ||
        api?.user?.username ||
        "Usuario";
      setProfileData((prev) => ({
        ...prev,
        name: fullName,
        email: api?.user?.email || "",
        position: api?.user?.rol || "",
        department: api?.curso_preceptor
          ? `Preceptor de: ${api.curso_preceptor}`
          : api?.alumno
          ? `Alumno: ${api.alumno.curso}`
          : api?.alumnos_del_padre && api.alumnos_del_padre.length
          ? "Responsable de alumnos"
          : "",
      }));
    }
  };

  const handleTogglePassword = () => {
    setShowPasswordForm((v) => !v);
    setPwdError("");
    setPwdOk("");
  };

  const resetPasswordForm = () => {
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
    setPwdError("");
    setPwdOk("");
  };

  const showToast = (type, message, ttl = 3000) => {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    setToast({ type, message });
    toastTimerRef.current = setTimeout(() => setToast(null), ttl);
  };

  useEffect(() => {
    return () => {
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
      if (logoutTimerRef.current) clearTimeout(logoutTimerRef.current);
    };
  }, []);

  const handleChangePassword = async (e) => {
    e?.preventDefault?.();
    setPwdError("");
    setPwdOk("");

    if (!currentPassword || !newPassword) {
      showToast("error", "Completá la contraseña actual y la nueva.");
      return;
    }
    if (newPassword.length < 6) {
      showToast("error", "La contraseña nueva debe tener al menos 6 caracteres.");
      return;
    }
    if (newPassword !== confirmPassword) {
      showToast("error", "Las contraseñas nuevas no coinciden.");
      return;
    }

    setPwdLoading(true);
    try {
      const res = await authFetch("/auth/password-change/", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });

      const j = await res.json().catch(() => ({}));
      if (!res.ok) {
        showToast("error", j?.detail || "No se pudo cambiar la contraseña.");
        return;
      }

      showToast("success", j?.detail || "Contraseña actualizada. Se cerrará la sesión.");
      resetPasswordForm();
      setShowPasswordForm(false);
      if (logoutTimerRef.current) clearTimeout(logoutTimerRef.current);
      logoutTimerRef.current = setTimeout(() => {
        logout();
      }, 1200);
    } catch {
      showToast("error", "No se pudo conectar con el servidor.");
    } finally {
      setPwdLoading(false);
    }
  };

  async function refreshPerfilApi() {
    try {
      const res = await authFetch("/perfil_api/", {
        headers: { Accept: "application/json" },
      });
      if (!res.ok) return;
      const data = await res.json().catch(() => null);
      if (!data) return;

      setApi(data);

      const fullName =
        [data?.user?.first_name, data?.user?.last_name]
          .filter(Boolean)
          .join(" ") ||
        data?.user?.username ||
        "Usuario";

      setProfileData({
        name: fullName,
        email: data?.user?.email || "",
        position: data?.user?.rol || "",
        department: data?.curso_preceptor
          ? `Preceptor de: ${data.curso_preceptor}`
          : data?.alumno
          ? `Alumno: ${data.alumno.curso}`
          : data?.alumnos_del_padre && data.alumnos_del_padre.length
          ? "Responsable de alumnos"
          : "",
      });
    } catch {
      // silencio
    }
  }

  async function handleVincularLegajo(e) {
    e?.preventDefault?.();
    setLinkError("");
    setLinkOk("");

    const value = (legajo || "").trim();
    if (!value) {
      setLinkError("Ingresá tu legajo / id_alumno.");
      return;
    }

    setLinking(true);
    try {
      // ✅ Endpoint agregado en backend: /api/alumnos/vincular/
      // OJO: authFetch ya agrega /api, por eso acá va "/alumnos/vincular/"
      const res = await authFetch("/alumnos/vincular/", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ id_alumno: value }),
      });

      const j = await res.json().catch(() => ({}));
      if (!res.ok) {
        setLinkError(j?.detail || `No se pudo vincular (HTTP ${res.status}).`);
        return;
      }

      setLinkOk(
        j?.already_linked
          ? "Ya estabas vinculado a este alumno."
          : "Listo. Se vinculó tu usuario con el alumno."
      );

      await refreshPerfilApi();
    } catch {
      setLinkError("No se pudo vincular. Revisá tu conexión y volvé a intentar.");
    } finally {
      setLinking(false);
    }
  }

  const shouldShowVincular =
    !loading &&
    !error &&
    api &&
    isAlumno &&
    !api?.curso_preceptor &&
    !api?.alumnos_del_padre?.length &&
    !api?.alumno;

  return (
    <div className="space-y-6">
      {toast && (
        <div className="fixed top-4 right-4 z-50">
          <div
            className={`rounded-md px-4 py-3 text-sm shadow-lg border ${
              toast.type === "success"
                ? "bg-green-50 text-green-800 border-green-200"
                : "bg-red-50 text-red-800 border-red-200"
            }`}
          >
            {toast.message}
          </div>
        </div>
      )}
      {/* Header */}
      <div className="bg-blue-600 text-white px-6 py-4">
        <div className="flex items-center justify-between max-w-6xl mx-auto">
          <div className="flex items-center gap-3">
            <Link href="/dashboard" className="inline-flex">
              <div className="w-10 h-10 bg-white rounded-full flex items-center justify-center overflow-hidden">
                <img
                  src={LOGO_SRC}
                  alt="Escuela Santa Teresa"
                  className="h-full w-full object-contain"
                />
              </div>
            </Link>
            <h1 className="text-xl font-semibold">Perfil de usuario</h1>
          </div>

          {/* User Bar + Volver al panel */}
          <div className="flex items-center gap-2 sm:gap-3">
            <Link href="/dashboard">
              <Button variant="ghost" className="text-white hover:bg-blue-700 gap-2">
                <ArrowLeft className="h-4 w-4" />
                <span className="hidden sm:inline">Volver al panel</span>
              </Button>
            </Link>

            {/* Campanita con menú de notificaciones */}
            <NotificationBell unreadCount={unreadCount} />

            {/* Mail con badge y link a mensajes */}
            <div className="relative">
              <Link href="/mensajes">
                <Button
                  variant="ghost"
                  size="icon"
                  className="text-white hover:bg-blue-700"
                >
                  <Mail className="h-5 w-5" />
                </Button>
              </Link>
              {unreadCount > 0 && (
                <span className="absolute -top-1 -right-1 text-[10px] leading-none px-1.5 py-0.5 rounded-full bg-red-600 text-white border border-white">
                  {unreadCount > 99 ? "99+" : unreadCount}
                </span>
              )}
            </div>

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" className="text-white hover:bg-blue-700 gap-2">
                  <User className="h-4 w-4" />
                  {displayName}
                  <ChevronDown className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuItem asChild className="text-sm">
                  <Link href="/perfil">
                    <div className="flex items-center">
                      <User className="h-4 w-4 mr-2" />
                      Perfil
                    </div>
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuItem
                  className="text-sm"
                  onClick={() => {
                    try {
                      localStorage.clear();
                    } catch {}
                    window.location.href = "/login";
                  }}
                >
                  <span className="h-4 w-4 mr-2">🚪</span>
                  Cerrar sesión
                </DropdownMenuItem>
                <div className="px-3 py-2 text-xs text-muted-foreground border-t">
                  Grupos: {gruposTexto}
                </div>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="space-y-6">
        {loading ? (
          <div className="text-sm text-gray-600">Cargando perfil…</div>
        ) : error ? (
          <div className="text-sm text-red-600">Error: {String(error)}</div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            {/* Columna izquierda — Avatar y datos rápidos */}
            <div className="lg:col-span-1">
              <Card className="shadow-sm border-0 bg-white/80 backdrop-blur-sm">
                <CardContent className="p-6 text-center">
                  <div className="relative inline-block mb-4">
                    <div className="w-32 h-32 bg-blue-100 rounded-full flex items-center justify-center mx-auto">
                      <User className="h-16 w-16 text-blue-600" />
                    </div>
                    <Button
                      size="icon"
                      className="absolute bottom-0 right-0 rounded-full w-10 h-10 bg-[#0c1b3f] hover:bg-[#0a1736]"
                      disabled
                    >
                      <Camera className="h-4 w-4" />
                    </Button>
                  </div>
                  <h3 className="font-semibold text-gray-900 text-lg mb-1">
                    {displayName}
                  </h3>
                  <p className="text-sm text-gray-600 mb-2">{rolPrincipal}</p>
                  

                  
                </CardContent>
              </Card>

              {/* ✅ FIX: si no se detecta alumno automáticamente, damos un vínculo explícito */}
              {shouldShowVincular && (
                <Card className="mt-6 shadow-sm border-0 bg-white/80 backdrop-blur-sm">
                  <CardContent className="p-6">
                    <div className="flex items-start gap-3">
                      <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center flex-shrink-0">
                        <Link2 className="h-6 w-6 text-blue-600" />
                      </div>
                      <div className="w-full">
                        <h3 className="font-semibold text-gray-900 text-lg">
                          Vincular mi legajo
                        </h3>
                        <p className="text-sm text-gray-600 mt-1">
                          Para que el sistema sepa quién sos (y puedas ver tus notas,
                          asistencias, sanciones y calendario), vinculá tu usuario con tu
                          registro de alumno usando tu <b>id_alumno / legajo</b>.
                        </p>

                        <form onSubmit={handleVincularLegajo} className="mt-4 space-y-3">
                          <div>
                            <Label htmlFor="legajo" className="text-sm font-medium text-gray-700">
                              Legajo / ID de alumno
                            </Label>
                            <Input
                              id="legajo"
                              value={legajo}
                              onChange={(e) => setLegajo(e.target.value)}
                              placeholder="Ej: 1A-024"
                              className="mt-1"
                            />
                          </div>

                          {linkError && (
                            <div className="text-sm text-red-600">{linkError}</div>
                          )}
                            {linkOk && <SuccessMessage className="mt-1">{linkOk}</SuccessMessage>}

                          <Button
                            type="submit"
                            disabled={linking}
                            className="bg-[#0c1b3f] hover:bg-[#0a1736]"
                          >
                            {linking ? "Vinculando…" : "Vincular"}
                          </Button>
                        </form>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )}

            </div>

            {/* Columna derecha — Información personal */}
            <div className="lg:col-span-2">
              <Card className="shadow-sm border-0 bg-white/80 backdrop-blur-sm">
                <CardContent className="p-6">
                  <div className="flex items-center justify-between mb-6">
                    <h4 className="font-semibold text-gray-900 text-lg">
                      Información personal
                    </h4>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        onClick={handleTogglePassword}
                      >
                        <KeyRound className="h-4 w-4 mr-2" />
                        Cambiar contraseña
                      </Button>
                      {isEditing ? (
                        <>
                          <Button
                            size="sm"
                            onClick={handleSave}
                            className="bg-[#0c1b3f] hover:bg-[#0a1736]"
                            disabled={saving}
                          >
                            <Save className="h-4 w-4 mr-2" />
                            {saving ? "Guardando..." : "Guardar"}
                          </Button>
                          <Button
                            size="sm"
                            onClick={handleCancel}
                          >
                            <X className="h-4 w-4 mr-2" />
                            Cancelar
                          </Button>
                        </>
                      ) : (
                        <Button
                          size="sm"
                          onClick={() => setIsEditing(true)}
                        >
                          <Edit3 className="h-4 w-4 mr-2" />
                          Editar
                        </Button>
                      )}
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div>
                      <Label
                        htmlFor="name"
                        className="text-sm font-medium text-gray-700"
                      >
                        Nombre completo
                      </Label>
                      {isEditing ? (
                        <Input
                          id="name"
                          value={profileData.name}
                          onChange={(e) =>
                            setProfileData({
                              ...profileData,
                              name: e.target.value,
                            })
                          }
                          className="mt-1"
                        />
                      ) : (
                        <p className="mt-1 text-gray-900">
                          {profileData.name || "—"}
                        </p>
                      )}
                    </div>

                    <div>
                      <Label
                        htmlFor="email"
                        className="text-sm font-medium text-gray-700"
                      >
                        Correo
                      </Label>
                      {isEditing ? (
                        <Input
                          id="email"
                          type="email"
                          value={profileData.email}
                          onChange={(e) =>
                            setProfileData({
                              ...profileData,
                              email: e.target.value,
                            })
                          }
                          className="mt-1"
                        />
                      ) : (
                        <p className="mt-1 text-gray-900 break-all">
                          {profileData.email || "—"}
                        </p>
                      )}
                    </div>

                    <div className="md:col-span-2">
                      <Label
                        htmlFor="department"
                        className="text-sm font-medium text-gray-700"
                      >
                        Curso
                      </Label>
                      {isEditing ? (
                        <Input
                          id="department"
                          value={profileData.department}
                          onChange={(e) =>
                            setProfileData({
                              ...profileData,
                              department: e.target.value,
                            })
                          }
                          className="mt-1"
                        />
                      ) : (
                        <p className="mt-1 text-gray-900">
                          {cursoAlumnoTexto || "—"}
                        </p>
                      )}
                    </div>
                  </div>

                  {showPasswordForm && (
                    <div className="mt-8 border-t pt-6">
                      <h5 className="font-semibold text-gray-900 text-base mb-4">
                        Cambiar contraseña
                      </h5>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <div>
                          <Label
                            htmlFor="currentPassword"
                            className="text-sm font-medium text-gray-700"
                          >
                            Contraseña actual
                          </Label>
                          <Input
                            id="currentPassword"
                            type="password"
                            value={currentPassword}
                            onChange={(e) => setCurrentPassword(e.target.value)}
                            className="mt-1"
                            autoComplete="current-password"
                          />
                        </div>
                        <div>
                          <Label
                            htmlFor="newPassword"
                            className="text-sm font-medium text-gray-700"
                          >
                            Contraseña nueva
                          </Label>
                          <Input
                            id="newPassword"
                            type="password"
                            value={newPassword}
                            onChange={(e) => setNewPassword(e.target.value)}
                            className="mt-1"
                            autoComplete="new-password"
                          />
                        </div>
                        <div>
                          <Label
                            htmlFor="confirmPassword"
                            className="text-sm font-medium text-gray-700"
                          >
                            Repetir contraseña nueva
                          </Label>
                          <Input
                            id="confirmPassword"
                            type="password"
                            value={confirmPassword}
                            onChange={(e) => setConfirmPassword(e.target.value)}
                            className="mt-1"
                            autoComplete="new-password"
                          />
                        </div>
                      </div>

                      <div className="mt-4 flex flex-wrap gap-2">
                        <Button
                          size="sm"
                          className="bg-[#0c1b3f] hover:bg-[#0a1736]"
                          onClick={handleChangePassword}
                          disabled={pwdLoading}
                        >
                          {pwdLoading ? "Guardando…" : "Actualizar contraseña"}
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => {
                            setShowPasswordForm(false);
                            resetPasswordForm();
                          }}
                        >
                          Cancelar
                        </Button>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>

              {api?.alumnos_del_padre &&
                api.alumnos_del_padre.length > 0 && (
                  <Card className="mt-8 shadow-sm border-0 bg-white/80 backdrop-blur-sm">
                    <CardContent className="p-6">
                      <h4 className="font-semibold text-gray-900 text-lg mb-4">
                        Alumnos a cargo
                      </h4>
                      <ul className="text-sm text-gray-800 list-disc pl-5 space-y-1">
                        {api.alumnos_del_padre.map((a) => (
                          <li key={a.id}>
                            {a.nombre} — {a.curso} (ID: {a.id_alumno})
                          </li>
                        ))}
                      </ul>
                    </CardContent>
                  </Card>
                )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}



