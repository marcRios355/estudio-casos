from datetime import date
from decimal import Decimal
from tempfile import TemporaryDirectory

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .admin import PagoInline, PagoInlineForm
from .models import Caso, Cliente, EstadoCaso, Expediente, Pago


class PagoValidationTests(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(
            nombres="Cliente de prueba",
            documento="12345678",
            telefono="999999999",
            correo="cliente@example.com",
        )
        self.estado = EstadoCaso.objects.create(
            nombre="Archivado",
            permite_pagos=False,
        )
        self.caso = Caso.objects.create(
            codigo="TEST-001",
            titulo="Caso archivado",
            descripcion="Caso usado para probar el bloqueo de pagos.",
            fecha_inicio=date(2026, 1, 1),
            cliente=self.cliente,
            estado=self.estado,
        )

    def test_save_rejects_pago_when_case_disallows_payments(self):
        pago = Pago(
            caso=self.caso,
            monto=Decimal("100.00"),
            fecha=date(2026, 1, 2),
            descripcion="Pago que debe rechazarse",
        )

        with self.assertRaises(ValidationError):
            pago.save()

        self.assertFalse(Pago.objects.exists())

    def test_pago_inline_shows_validation_error(self):
        user_model = get_user_model()
        user_model.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="password",
        )
        client = Client()
        client.login(username="admin", password="password")
        url = reverse("admin:casos_caso_change", args=[self.caso.pk])
        get_response = client.get(url)
        self.assertEqual(get_response.status_code, 200)

        formset_prefixes = {
            inline_admin_formset.opts.model: inline_admin_formset.formset.prefix
            for inline_admin_formset in get_response.context["inline_admin_formsets"]
        }
        pagos_prefix = formset_prefixes[Pago]

        post_data = {
            "codigo": self.caso.codigo,
            "titulo": self.caso.titulo,
            "descripcion": self.caso.descripcion,
            "fecha_inicio": self.caso.fecha_inicio.isoformat(),
            "cliente": str(self.cliente.pk),
            "estado": str(self.estado.pk),
            "_save": "Guardar",
        }
        for inline_admin_formset in get_response.context["inline_admin_formsets"]:
            prefix = inline_admin_formset.formset.prefix
            total_forms = inline_admin_formset.formset.total_form_count()
            if inline_admin_formset.opts.model is Pago:
                total_forms = 1
            post_data.update(
                {
                    f"{prefix}-TOTAL_FORMS": str(total_forms),
                    f"{prefix}-INITIAL_FORMS": str(
                        inline_admin_formset.formset.initial_form_count()
                    ),
                    f"{prefix}-MIN_NUM_FORMS": "0",
                    f"{prefix}-MAX_NUM_FORMS": "1000",
                }
            )

        post_data.update(
            {
                f"{pagos_prefix}-0-monto": "100.00",
                f"{pagos_prefix}-0-fecha": "2026-01-02",
                f"{pagos_prefix}-0-descripcion": "Pago desde el inline",
            }
        )
        response = client.post(url, post_data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Error: El estado actual del caso (&#x27;Archivado&#x27;) "
            "no admite pagos.",
        )
        self.assertFalse(Pago.objects.exists())

    def test_pago_inline_form_validates_parent_case(self):
        form = PagoInlineForm(
            data={
                "caso": str(self.caso.pk),
                "monto": "100.00",
                "fecha": "2026-01-02",
                "descripcion": "Pago desde el formulario inline",
            },
            instance=Pago(caso=self.caso),
        )
        form.parent_object = self.caso

        self.assertFalse(form.is_valid())
        self.assertIn(
            "El estado actual del caso",
            str(form.errors.as_data()),
        )


class WebViewsTests(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(
            nombres="Lucía Ramos",
            documento="87654321",
            telefono="988777666",
            correo="lucia@example.com",
        )
        self.estado = EstadoCaso.objects.create(
            nombre="Archivado web",
            permite_pagos=False,
        )
        self.caso = Caso.objects.create(
            codigo="WEB-001",
            titulo="Caso web archivado",
            descripcion="Caso de prueba de las páginas públicas.",
            fecha_inicio=date(2026, 3, 1),
            cliente=self.cliente,
            estado=self.estado,
        )

    def test_cliente_crud_uses_get_for_forms_and_post_for_mutations(self):
        response = self.client.get(reverse("casos:lista_clientes"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.cliente.nombres)

        response = self.client.get(reverse("casos:crear_cliente"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "csrfmiddlewaretoken")

        response = self.client.post(
            reverse("casos:crear_cliente"),
            {
                "nombres": "Cliente nuevo",
                "documento": "11223344",
                "telefono": "900111222",
                "correo": "nuevo@example.com",
            },
        )
        self.assertRedirects(response, reverse("casos:lista_clientes"))
        cliente_nuevo = Cliente.objects.get(documento="11223344")

        response = self.client.post(
            reverse("casos:editar_cliente", args=[cliente_nuevo.pk]),
            {
                "nombres": "Cliente actualizado",
                "documento": cliente_nuevo.documento,
                "telefono": cliente_nuevo.telefono,
                "correo": cliente_nuevo.correo,
            },
        )
        self.assertRedirects(response, reverse("casos:lista_clientes"))
        cliente_nuevo.refresh_from_db()
        self.assertEqual(cliente_nuevo.nombres, "Cliente actualizado")

        response = self.client.get(
            reverse("casos:eliminar_cliente", args=[cliente_nuevo.pk])
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            reverse("casos:eliminar_cliente", args=[cliente_nuevo.pk])
        )
        self.assertRedirects(response, reverse("casos:lista_clientes"))
        self.assertFalse(Cliente.objects.filter(pk=cliente_nuevo.pk).exists())

    def test_case_list_and_detail_render_summary_dates_and_payment_alert(self):
        Expediente.objects.create(
            numero="EXP-WEB-001",
            juzgado="Juzgado de prueba",
            fecha_presentacion=date(2026, 3, 5),
            caso=self.caso,
        )

        response = self.client.get(reverse("casos:lista_casos"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.caso.codigo)
        self.assertContains(response, "0.00")

        response = self.client.get(
            reverse("casos:detalle_caso", args=[self.caso.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Este caso no admite pagos")
        self.assertContains(response, "05/03/2026")
        self.assertContains(response, "Este caso no tiene pagos registrados.")

        estado_activo = EstadoCaso.objects.create(
            nombre="En trámite web",
            permite_pagos=True,
        )
        caso_activo = Caso.objects.create(
            codigo="WEB-002",
            titulo="Caso web activo",
            descripcion="Caso con pago permitido.",
            fecha_inicio=date(2026, 3, 1),
            cliente=self.cliente,
            estado=estado_activo,
        )
        Pago.objects.create(
            caso=caso_activo,
            monto=Decimal("25.50"),
            fecha=date(2026, 3, 7),
            descripcion="Pago de prueba",
        )
        response = self.client.get(
            reverse("casos:detalle_caso", args=[caso_activo.pk])
        )
        self.assertContains(response, "07/03/2026")
        self.assertContains(response, "Pago de prueba")

    def test_case_list_filters_by_query_and_remembers_cookie(self):
        estado_activo = EstadoCaso.objects.create(
            nombre="En trámite filtro",
            permite_pagos=True,
        )
        caso_activo = Caso.objects.create(
            codigo="WEB-FILTRO",
            titulo="Caso filtrable",
            descripcion="Caso para probar el filtro.",
            fecha_inicio=date(2026, 3, 2),
            cliente=self.cliente,
            estado=estado_activo,
        )

        response = self.client.get(
            reverse("casos:lista_casos"),
            {"estado": estado_activo.pk},
        )
        self.assertContains(response, caso_activo.codigo)
        self.assertNotContains(response, self.caso.codigo)
        self.assertEqual(
            response.cookies["ultimo_estado"].value,
            str(estado_activo.pk),
        )

        self.client.cookies["ultimo_estado"] = str(estado_activo.pk)
        response = self.client.get(reverse("casos:lista_casos"))
        self.assertContains(response, caso_activo.codigo)
        self.assertNotContains(response, self.caso.codigo)

    def test_case_detail_registers_and_blocks_payments(self):
        detail_url = reverse("casos:detalle_caso", args=[self.caso.pk])
        response = self.client.post(
            detail_url,
            {
                "accion": "registrar_pago",
                "monto": "10.00",
                "fecha": "2026-03-10",
                "descripcion": "Pago bloqueado",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Pago.objects.exists())
        self.assertContains(response, "Este caso no admite pagos.")
        self.assertContains(response, "Intentar registrar pago")

        estado_activo = EstadoCaso.objects.create(
            nombre="En trámite pago web",
            permite_pagos=True,
        )
        caso_activo = Caso.objects.create(
            codigo="WEB-PAGO",
            titulo="Caso para pago web",
            descripcion="Pago vía formulario web.",
            fecha_inicio=date(2026, 3, 3),
            cliente=self.cliente,
            estado=estado_activo,
        )
        response = self.client.post(
            reverse("casos:detalle_caso", args=[caso_activo.pk]),
            {
                "accion": "registrar_pago",
                "monto": "10.00",
                "fecha": "2026-03-10",
                "descripcion": "Pago permitido",
            },
            follow=True,
        )
        self.assertRedirects(
            response,
            reverse("casos:detalle_caso", args=[caso_activo.pk]),
        )
        self.assertContains(response, "Pago registrado con éxito")
        self.assertTrue(
            Pago.objects.filter(caso=caso_activo, monto=Decimal("10.00")).exists()
        )

    def test_case_detail_uploads_expediente_document(self):
        detail_url = reverse("casos:detalle_caso", args=[self.caso.pk])
        uploaded = SimpleUploadedFile(
            "demanda.txt",
            b"Contenido de prueba",
            content_type="text/plain",
        )
        with TemporaryDirectory() as media_directory:
            with override_settings(MEDIA_ROOT=media_directory):
                response = self.client.post(
                    detail_url,
                    {
                        "accion": "adjuntar_expediente",
                        "numero": "EXP-WEB-UPLOAD",
                        "juzgado": "Juzgado de prueba",
                        "fecha_presentacion": "2026-03-11",
                        "documento": uploaded,
                    },
                )

        self.assertRedirects(response, detail_url)
        expediente = Expediente.objects.get(numero="EXP-WEB-UPLOAD")
        self.assertTrue(expediente.documento.name.endswith("demanda.txt"))

    def test_case_api_returns_requested_json_fields(self):
        Expediente.objects.create(
            numero="EXP-API-001",
            juzgado="Juzgado API",
            fecha_presentacion=date(2026, 3, 12),
            caso=self.caso,
        )
        response = self.client.get(
            reverse("casos:api_caso", args=[self.caso.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "codigo": self.caso.codigo,
                "cliente": self.cliente.nombres,
                "estado": self.estado.nombre,
                "abogados": [],
                "numero_expedientes": 1,
                "total_pagado": 0.0,
            },
        )

# Create your tests here.
