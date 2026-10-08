from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum


class Cliente(models.Model):
    nombres = models.CharField(max_length=200)
    documento = models.CharField(
        max_length=11,
        unique=True,
        help_text="DNI o RUC del cliente.",
    )
    telefono = models.CharField(max_length=20)
    correo = models.EmailField()

    def __str__(self):
        return f"{self.nombres} ({self.documento})"


class EstadoCaso(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    permite_pagos = models.BooleanField(default=True)

    def __str__(self):
        return self.nombre


class PerfilAbogado(models.Model):
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="perfil_abogado",
    )
    numero_colegiatura = models.CharField(max_length=50)
    especialidad = models.CharField(max_length=150)

    def __str__(self):
        return (
            f"{self.usuario.get_full_name() or self.usuario.get_username()} "
            f"- {self.numero_colegiatura}"
        )


class Caso(models.Model):
    """
    Los clientes y estados se protegen para evitar eliminar referencias usadas
    por casos. SET_NULL no aplica porque ambas relaciones son obligatorias.
    """

    codigo = models.CharField(max_length=50, unique=True)
    titulo = models.CharField(max_length=200)
    descripcion = models.TextField()
    fecha_inicio = models.DateField()
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name="casos",
    )
    estado = models.ForeignKey(
        EstadoCaso,
        on_delete=models.PROTECT,
        related_name="casos",
    )
    abogados = models.ManyToManyField(
        PerfilAbogado,
        related_name="casos",
        blank=True,
    )

    def total_pagado(self):
        total = self.pagos.aggregate(total=Sum("monto"))["total"]
        return total if total is not None else Decimal("0.00")

    def __str__(self):
        return f"{self.codigo} - {self.titulo}"


class Expediente(models.Model):
    numero = models.CharField(max_length=50, unique=True)
    juzgado = models.CharField(max_length=200)
    fecha_presentacion = models.DateField()
    caso = models.ForeignKey(
        Caso,
        on_delete=models.CASCADE,
        related_name="expedientes",
    )
    documento = models.FileField(
        upload_to="expedientes/",
        null=True,
        blank=True,
    )

    def __str__(self):
        return f"{self.numero} - {self.juzgado}"


class Pago(models.Model):
    """Los pagos se eliminan en cascada porque pertenecen a un único caso."""

    caso = models.ForeignKey(
        Caso,
        on_delete=models.CASCADE,
        related_name="pagos",
    )
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    fecha = models.DateField()
    descripcion = models.CharField(max_length=250)

    def clean(self):
        super().clean()
        if (
            hasattr(self, "caso")
            and self.caso
            and self.caso.estado
            and not self.caso.estado.permite_pagos
        ):
            raise ValidationError(
                {
                    "monto": (
                        "No se pueden registrar pagos. El estado del caso "
                        f"'{self.caso.estado.nombre}' no permite pagos."
                    )
                }
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.caso.codigo} - {self.monto} ({self.fecha})"
