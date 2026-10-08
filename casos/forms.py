from django import forms

from .models import Cliente, Expediente, Pago


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ("nombres", "documento", "telefono", "correo")
        widgets = {
            "nombres": forms.TextInput(attrs={"class": "form-control"}),
            "documento": forms.TextInput(attrs={"class": "form-control"}),
            "telefono": forms.TextInput(attrs={"class": "form-control"}),
            "correo": forms.EmailInput(attrs={"class": "form-control"}),
        }


class PagoForm(forms.ModelForm):
    class Meta:
        model = Pago
        fields = ("monto", "fecha", "descripcion")
        widgets = {
            "monto": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0.01"}
            ),
            "fecha": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}
            ),
            "descripcion": forms.TextInput(attrs={"class": "form-control"}),
        }


class ExpedienteForm(forms.ModelForm):
    class Meta:
        model = Expediente
        fields = ("numero", "juzgado", "fecha_presentacion", "documento")
        widgets = {
            "numero": forms.TextInput(attrs={"class": "form-control"}),
            "juzgado": forms.TextInput(attrs={"class": "form-control"}),
            "fecha_presentacion": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}
            ),
            "documento": forms.ClearableFileInput(
                attrs={"class": "form-control"}
            ),
        }
