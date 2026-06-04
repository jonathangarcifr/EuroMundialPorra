from django import forms
from .models import Apuesta, Partido
from .choices import BOMBO_1, BOMBO_2, BOMBO_3, BOMBO_4, BOMBO_5, BOMBO_6, TODOS_EQUIPOS


OPCION_VACIA = [("", "Elija una selección")]

BANDERAS = {
    "Alemania": "🇩🇪",
    "Argentina": "🇦🇷",
    "Brasil": "🇧🇷",
    "España": "🇪🇸",
    "Francia": "🇫🇷",
    "Holanda": "🇳🇱",
    "Inglaterra": "🏴",
    "Portugal": "🇵🇹",
    "Bélgica": "🇧🇪",
    "Colombia": "🇨🇴",
    "Croacia": "🇭🇷",
    "Marruecos": "🇲🇦",
    "Noruega": "🇳🇴",
    "Senegal": "🇸🇳",
    "Turquía": "🇹🇷",
    "Uruguay": "🇺🇾",
    "Austria": "🇦🇹",
    "Ecuador": "🇪🇨",
    "Escocia": "🏴",
    "EEUU": "🇺🇸",
    "Japón": "🇯🇵",
    "México": "🇲🇽",
    "Suecia": "🇸🇪",
    "Suiza": "🇨🇭",
    "Argelia": "🇩🇿",
    "Australia": "🇦🇺",
    "Canadá": "🇨🇦",
    "Corea del Sur": "🇰🇷",
    "Costa de Marfil": "🇨🇮",
    "Egipto": "🇪🇬",
    "Irán": "🇮🇷",
    "Rep. Checa": "🇨🇿",
    "Bosnia": "🇧🇦",
    "Congo": "🇨🇩",
    "Ghana": "🇬🇭",
    "Panamá": "🇵🇦",
    "Paraguay": "🇵🇾",
    "Qatar": "🇶🇦",
    "Sudáfrica": "🇿🇦",
    "Túnez": "🇹🇳",
    "Arabia Saudí": "🇸🇦",
    "Cabo Verde": "🇨🇻",
    "Curaçao": "🇨🇼",
    "Haití": "🇭🇹",
    "Irak": "🇮🇶",
    "Jordania": "🇯🇴",
    "Nueva Zelanda": "🇳🇿",
    "Uzbekistán": "🇺🇿",
}


def con_bandera(lista):
    return [
        (valor, valor)
        for valor, _ in lista
    ]


class ApuestaForm(forms.ModelForm):
    bombo_1 = forms.MultipleChoiceField(
        choices=con_bandera(BOMBO_1),
        widget=forms.CheckboxSelectMultiple,
        label="Bombo 1"
    )
    bombo_2 = forms.MultipleChoiceField(
        choices=con_bandera(BOMBO_2),
        widget=forms.CheckboxSelectMultiple,
        label="Bombo 2"
    )
    bombo_3 = forms.MultipleChoiceField(
        choices=con_bandera(BOMBO_3),
        widget=forms.CheckboxSelectMultiple,
        label="Bombo 3"
    )
    bombo_4 = forms.MultipleChoiceField(
        choices=con_bandera(BOMBO_4),
        widget=forms.CheckboxSelectMultiple,
        label="Bombo 4"
    )
    bombo_5 = forms.MultipleChoiceField(
        choices=con_bandera(BOMBO_5),
        widget=forms.CheckboxSelectMultiple,
        label="Bombo 5"
    )
    bombo_6 = forms.MultipleChoiceField(
        choices=con_bandera(BOMBO_6),
        widget=forms.CheckboxSelectMultiple,
        label="Bombo 6"
    )

    equipo_goleador = forms.ChoiceField(
        choices=OPCION_VACIA + con_bandera(sorted(TODOS_EQUIPOS, key=lambda equipo: equipo[1])),
        label="Equipo del goleador"
    )

    class Meta:
        model = Apuesta
        fields = [
            "nombre",
            "email",
            "pagado",
            "bombo_1",
            "bombo_2",
            "bombo_3",
            "bombo_4",
            "bombo_5",
            "bombo_6",
            "goleador",
            "equipo_goleador",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            self.fields["bombo_1"].initial = [self.instance.equipo_1, self.instance.equipo_2]
            self.fields["bombo_2"].initial = [self.instance.equipo_3, self.instance.equipo_4]
            self.fields["bombo_3"].initial = [self.instance.equipo_5, self.instance.equipo_6]
            self.fields["bombo_4"].initial = [self.instance.equipo_7, self.instance.equipo_8]
            self.fields["bombo_5"].initial = [self.instance.equipo_9, self.instance.equipo_10]
            self.fields["bombo_6"].initial = [self.instance.equipo_11, self.instance.equipo_12]

        for field_name, field in self.fields.items():
            if field_name == "pagado":
                field.widget.attrs.update({
                    "class": "form-check-input pagado-check",
                    "autocomplete": "off",
                })
            elif field_name.startswith("bombo_"):
                field.widget.attrs.update({
                    "class": "bombo-checkbox-list",
                })
            else:
                field.widget.attrs.update({
                    "class": "form-control",
                    "autocomplete": "off",
                })

        self.fields["nombre"].widget.attrs.update({
            "placeholder": "Indique su nombre"
        })

        self.fields["email"].widget.attrs.update({
            "placeholder": "Indique su correo electrónico",
            "type": "email",
        })

        self.fields["goleador"].widget.attrs.update({
            "placeholder": "Indique su goleador seleccionado"
        })

    def clean(self):
        cleaned_data = super().clean()

        bombos = [
            "bombo_1",
            "bombo_2",
            "bombo_3",
            "bombo_4",
            "bombo_5",
            "bombo_6",
        ]

        equipos = []

        for bombo in bombos:
            seleccionados = cleaned_data.get(bombo, [])

            if len(seleccionados) != 2:
                self.add_error(
                    bombo,
                    f"Debe seleccionar exactamente dos selecciones en {self.fields[bombo].label}."
                )

            equipos.extend(seleccionados)

        equipo_goleador = cleaned_data.get("equipo_goleador")

        if equipo_goleador in equipos:
            self.add_error(
                "equipo_goleador",
                "El equipo del goleador no puede coincidir con ninguno de los 12 equipos seleccionados."
            )

        return cleaned_data

    def save(self, commit=True):
        apuesta = super().save(commit=False)

        bombo_1 = self.cleaned_data["bombo_1"]
        bombo_2 = self.cleaned_data["bombo_2"]
        bombo_3 = self.cleaned_data["bombo_3"]
        bombo_4 = self.cleaned_data["bombo_4"]
        bombo_5 = self.cleaned_data["bombo_5"]
        bombo_6 = self.cleaned_data["bombo_6"]

        apuesta.equipo_1, apuesta.equipo_2 = bombo_1
        apuesta.equipo_3, apuesta.equipo_4 = bombo_2
        apuesta.equipo_5, apuesta.equipo_6 = bombo_3
        apuesta.equipo_7, apuesta.equipo_8 = bombo_4
        apuesta.equipo_9, apuesta.equipo_10 = bombo_5
        apuesta.equipo_11, apuesta.equipo_12 = bombo_6

        if commit:
            apuesta.save()

        return apuesta

class PartidoForm(forms.ModelForm):
    equipo_local = forms.ChoiceField(
        choices=OPCION_VACIA + sorted(TODOS_EQUIPOS, key=lambda equipo: equipo[1]),
        label="Equipo 1"
    )

    equipo_visitante = forms.ChoiceField(
        choices=OPCION_VACIA + sorted(TODOS_EQUIPOS, key=lambda equipo: equipo[1]),
        label="Equipo 2"
    )

    GRUPOS = [("", "Elija un grupo")] + [
        (f"Grupo {letra}", f"Grupo {letra}")
        for letra in "ABCDEFGHIJKL"
    ]

    grupo = forms.ChoiceField(
        choices=GRUPOS,
        label="Grupo"
    )

    class Meta:
        model = Partido
        fields = [
            "fase",
            "grupo",
            "fecha_partido",
            "equipo_local",
            "equipo_visitante",
        ]
        widgets = {
            "fecha_partido": forms.DateTimeInput(
                attrs={
                    "type": "datetime-local",
                },
                format="%Y-%m-%dT%H:%M"
            )
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            field.widget.attrs.update({
                "class": "form-control",
                "autocomplete": "off",
            })

    def clean(self):
        cleaned_data = super().clean()

        equipo_local = cleaned_data.get("equipo_local")
        equipo_visitante = cleaned_data.get("equipo_visitante")

        if equipo_local and equipo_visitante and equipo_local == equipo_visitante:
            self.add_error(
                "equipo_visitante",
                "El equipo 1 y el equipo 2 no pueden ser el mismo."
            )

        return cleaned_data