from django.shortcuts import redirect
from django.urls import reverse


class BloqueoEntreEdicionesMiddleware:
    """
    Mientras la competición esté bloqueada:

    - La ruta principal muestra siempre la cuenta atrás.
    - Los administradores pueden acceder al resto de la aplicación.
    - Los usuarios no administradores solo pueden acceder a:
        * Cuenta atrás.
        * Clasificación final.
        * Login/logout.
        * Administración.
        * Archivos estáticos.
    """

    RUTAS_PUBLICAS = (
        "/",
        "/cuentaatras/",
        "/clasificacion/",
        "/admin/",
        "/accounts/login/",
        "/accounts/logout/",
        "/static/",
        "/media/",
        "/favicon.ico",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = request.user
        ruta = request.path

        # La raíz siempre debe mostrar la cuenta atrás,
        # también para los administradores.
        if ruta == "/":
            return self.get_response(request)

        # Los administradores pueden acceder al resto de rutas,
        # incluido /inicio/.
        if usuario.is_authenticated and usuario.is_staff:
            return self.get_response(request)

        ruta_publica = any(
            ruta.startswith(ruta_permitida)
            for ruta_permitida in self.RUTAS_PUBLICAS
            if ruta_permitida != "/"
        )

        if not ruta_publica:
            return redirect(reverse("cuentaatras"))

        return self.get_response(request)