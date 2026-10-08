from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.db.models.deletion import ProtectedError
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET

from .forms import ClienteForm, ExpedienteForm, PagoForm
from .models import Caso, Cliente, EstadoCaso, Expediente, Pago


def lista_clientes(request):
    clientes = Cliente.objects.order_by("nombres")
    return render(request, "casos/clientes/lista.html", {"clientes": clientes})


def crear_cliente(request):
    if request.method == "POST":
        form = ClienteForm(request.POST)
        if form.is_valid():
            cliente = form.save()
            messages.success(request, f"Se creó el cliente {cliente.nombres}.")
            return redirect("casos:lista_clientes")
    else:
        form = ClienteForm()

    return render(
        request,
        "casos/clientes/formulario.html",
        {"form": form, "titulo": "Nuevo cliente"},
    )


def editar_cliente(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)
    if request.method == "POST":
        form = ClienteForm(request.POST, instance=cliente)
        if form.is_valid():
            form.save()
            messages.success(request, "Se actualizaron los datos del cliente.")
            return redirect("casos:lista_clientes")
    else:
        form = ClienteForm(instance=cliente)

    return render(
        request,
        "casos/clientes/formulario.html",
        {"form": form, "titulo": "Editar cliente", "cliente": cliente},
    )


def eliminar_cliente(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)
    if request.method == "POST":
        try:
            cliente.delete()
        except ProtectedError:
            messages.error(
                request,
                "No se puede eliminar este cliente porque tiene casos asociados.",
            )
        else:
            messages.success(request, "Se eliminó el cliente.")
        return redirect("casos:lista_clientes")

    return render(
        request,
        "casos/clientes/confirmar_eliminacion.html",
        {"cliente": cliente},
    )


def lista_casos(request):
    estado_id = None
    guardar_cookie = False
    limpiar_cookie = False
    if "estado" in request.GET:
        estado_solicitado = request.GET.get("estado", "").strip()
        if estado_solicitado.isdigit() and EstadoCaso.objects.filter(
            pk=estado_solicitado
        ).exists():
            estado_id = int(estado_solicitado)
            guardar_cookie = True
        elif not estado_solicitado:
            limpiar_cookie = True
        elif estado_solicitado:
            messages.warning(request, "El estado seleccionado no es válido.")
    else:
        estado_cookie = request.COOKIES.get("ultimo_estado", "")
        if estado_cookie.isdigit() and EstadoCaso.objects.filter(
            pk=estado_cookie
        ).exists():
            estado_id = int(estado_cookie)

    casos = (
        Caso.objects.select_related("cliente", "estado")
        .prefetch_related("abogados__usuario")
        .annotate(
            total_pagado_lista=Coalesce(
                Sum("pagos__monto"),
                Decimal("0.00"),
            )
        )
        .order_by("codigo")
    )
    if estado_id is not None:
        casos = casos.filter(estado_id=estado_id)

    response = render(
        request,
        "casos/lista_casos.html",
        {
            "casos": casos,
            "estados": EstadoCaso.objects.order_by("nombre"),
            "estado_seleccionado": estado_id,
        },
    )
    if guardar_cookie:
        response.set_cookie(
            "ultimo_estado",
            estado_id,
            max_age=60 * 60 * 24 * 30,
            httponly=True,
            samesite="Lax",
        )
    elif limpiar_cookie:
        response.delete_cookie("ultimo_estado", samesite="Lax")
    return response


def detalle_caso(request, pk):
    caso = get_object_or_404(
        Caso.objects.select_related("cliente", "estado").prefetch_related(
            "abogados__usuario",
            "expedientes",
            "pagos",
        ),
        pk=pk,
    )
    pago_form = PagoForm()
    expediente_form = ExpedienteForm()

    if request.method == "POST":
        accion = request.POST.get("accion")
        if accion == "registrar_pago":
            pago_form = PagoForm(request.POST, instance=Pago(caso=caso))
            if not caso.estado.permite_pagos:
                messages.error(request, "Este caso no admite pagos.")
            elif pago_form.is_valid():
                pago = pago_form.save(commit=False)
                pago.caso = caso
                try:
                    pago.save()
                except ValidationError as error:
                    pago_form.add_error(None, error)
                else:
                    messages.success(request, "Pago registrado con éxito")
                    return redirect("casos:detalle_caso", pk=caso.pk)
        elif accion == "adjuntar_expediente":
            expediente_form = ExpedienteForm(request.POST, request.FILES)
            if expediente_form.is_valid():
                expediente = expediente_form.save(commit=False)
                expediente.caso = caso
                expediente.save()
                messages.success(
                    request,
                    "El expediente y su documento se registraron correctamente.",
                )
                return redirect("casos:detalle_caso", pk=caso.pk)
        else:
            messages.error(request, "No se reconoció la operación solicitada.")

    return render(
        request,
        "casos/casos/detalle.html",
        {
            "caso": caso,
            "expedientes": caso.expedientes.all(),
            "pagos": caso.pagos.order_by("fecha"),
            "pago_form": pago_form,
            "expediente_form": expediente_form,
        },
    )


@require_GET
def api_caso(request, id):
    caso = get_object_or_404(
        Caso.objects.select_related("cliente", "estado").prefetch_related(
            "abogados__usuario",
            "expedientes",
        ),
        pk=id,
    )
    return JsonResponse(
        {
            "codigo": caso.codigo,
            "cliente": caso.cliente.nombres,
            "estado": caso.estado.nombre,
            "abogados": [
                abogado.usuario.get_full_name() or abogado.usuario.get_username()
                for abogado in caso.abogados.all()
            ],
            "numero_expedientes": caso.expedientes.count(),
            "total_pagado": float(caso.total_pagado()),
        }
    )
