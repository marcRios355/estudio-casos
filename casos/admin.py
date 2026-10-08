from django import forms
from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin

from .models import (
    Caso,
    Cliente,
    EstadoCaso,
    Expediente,
    Pago,
    PerfilAbogado,
)


class PerfilAbogadoInline(admin.StackedInline):
    model = PerfilAbogado
    can_delete = False
    extra = 0


class UserAdminConPerfilAbogado(UserAdmin):
    inlines = (*UserAdmin.inlines, PerfilAbogadoInline)


User = get_user_model()
admin.site.unregister(User)
admin.site.register(User, UserAdminConPerfilAbogado)


class ClienteTieneCasosFilter(SimpleListFilter):
    title = "casos asociados"
    parameter_name = "tiene_casos"

    def lookups(self, request, model_admin):
        return (
            ("si", "Con casos"),
            ("no", "Sin casos"),
        )

    def queryset(self, request, queryset):
        if self.value() == "si":
            return queryset.filter(casos__isnull=False).distinct()
        if self.value() == "no":
            return queryset.filter(casos__isnull=True)
        return queryset


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("nombres", "documento", "telefono", "correo")
    search_fields = ("nombres", "documento", "correo")
    list_filter = (ClienteTieneCasosFilter,)


@admin.register(EstadoCaso)
class EstadoCasoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "permite_pagos")
    search_fields = ("nombre",)
    list_filter = ("permite_pagos",)


class ExpedienteInline(admin.TabularInline):
    model = Expediente
    extra = 0


class PagoInlineForm(forms.ModelForm):
    class Meta:
        model = Pago
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()
        caso = self.get_caso_instance()
        if caso and caso.estado and not caso.estado.permite_pagos:
            raise forms.ValidationError(
                f"Error: El estado actual del caso ('{caso.estado.nombre}') "
                "no admite pagos."
            )
        return cleaned_data

    def get_caso_instance(self):
        caso = getattr(self.instance, "caso", None)
        if caso is not None:
            return caso
        return getattr(self, "parent_object", None)


class PagoInline(admin.TabularInline):
    model = Pago
    form = PagoInlineForm
    extra = 1

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)

        class FormsetWithParent(formset):
            def _construct_form(self, i, **form_kwargs):
                form = super()._construct_form(i, **form_kwargs)
                form.parent_object = obj
                return form

        return FormsetWithParent


@admin.register(Caso)
class CasoAdmin(admin.ModelAdmin):
    list_display = (
        "codigo",
        "titulo",
        "cliente",
        "estado",
        "total_pagado",
        "fecha_inicio",
    )
    search_fields = (
        "codigo",
        "titulo",
        "descripcion",
        "cliente__nombres",
        "cliente__documento",
    )
    list_filter = ("estado", "fecha_inicio")
    filter_horizontal = ("abogados",)
    inlines = (ExpedienteInline, PagoInline)


@admin.register(Expediente)
class ExpedienteAdmin(admin.ModelAdmin):
    list_display = ("numero", "juzgado", "fecha_presentacion", "caso")
    search_fields = ("numero", "juzgado", "caso__codigo", "caso__titulo")
    list_filter = ("juzgado", "fecha_presentacion")
