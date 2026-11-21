# -*- coding: utf-8 -*-
"""Stile unico delle finestre dei comandi (senza API Revit ne' WPF).

Le finestre (ui.xaml) non definiscono stili propri: al caricamento questo modulo mette
in <Window.Resources> gli stili condivisi, con la stessa tavolozza delle icone
(blu = azione principale, azzurro = evidenze, grigi = testi e bordi).

Uso nello script del pulsante:
    import stile_finestre as SF
    forms.WPFWindow.__init__(self, SF.xaml(xaml_file), literal_string=True)

Stili con nome da usare nei file ui.xaml:
    Intestazione  (Border)     riquadro blu in alto con titolo e sottotitolo bianchi
    Scheda        (Border)     riquadro bianco con bordo
    Etichetta     (TextBlock)  titoletto di una scheda (maiuscolo piccolo, grigio)
    Primario      (Button)     pulsante dell'azione principale
Tutti gli altri controlli (Button, CheckBox, RadioButton, TextBox, ComboBox, Expander)
prendono lo stile da soli.
"""
import io
import re

BLU = u"#1F6FB2"
BLU_SCURO = u"#185A91"
AZZURRO = u"#CFE3F4"
AZZURRO_CHIARO = u"#E8F1FA"
ARANCIO = u"#E5862A"
TESTO = u"#2B3640"
TESTO_SECONDARIO = u"#5B6B78"
BORDO = u"#C9D3DB"
BORDO_CHIARO = u"#DDE3E8"
SFONDO = u"#F5F7FA"
SFONDO_TENUE = u"#EEF2F5"

# Colori delle vecchie finestre -> tavolozza CDV. Verde, arancio e rosso (esiti) restano.
CONVERSIONE_COLORI = {
    u"#0284C7": BLU,
    u"#0369A1": BLU_SCURO,
    u"#7DD3FC": u"#8DB8DE",
    u"#E0F2FE": AZZURRO_CHIARO,
    u"#0F172A": TESTO,
    u"#1E293B": TESTO,
    u"#334155": u"#3C4650",
    u"#475569": u"#4A5866",
    u"#64748B": TESTO_SECONDARIO,
    u"#94A3B8": u"#8C9AA6",
    u"#CBD5E1": BORDO,
    u"#E2E8F0": BORDO_CHIARO,
    u"#F1F5F9": SFONDO_TENUE,
    u"#F8FAFC": SFONDO,
}

_P = u'<Setter Property="%s" Value="%s"/>'

RISORSE = (u"""<Window.Resources>
    <Style TargetType="Button">
        %(btn)s
        <Setter Property="Template">
            <Setter.Value>
                <ControlTemplate TargetType="Button">
                    <Border x:Name="bd" Background="{TemplateBinding Background}"
                            BorderBrush="{TemplateBinding BorderBrush}"
                            BorderThickness="{TemplateBinding BorderThickness}"
                            CornerRadius="4" Padding="{TemplateBinding Padding}">
                        <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
                    </Border>
                    <ControlTemplate.Triggers>
                        <Trigger Property="IsMouseOver" Value="True">
                            <Setter TargetName="bd" Property="Background" Value="%(hover)s"/>
                            <Setter TargetName="bd" Property="BorderBrush" Value="%(blu)s"/>
                        </Trigger>
                        <Trigger Property="IsPressed" Value="True">
                            <Setter TargetName="bd" Property="Background" Value="%(azzurro)s"/>
                        </Trigger>
                        <Trigger Property="IsEnabled" Value="False">
                            <Setter Property="Opacity" Value="0.45"/>
                        </Trigger>
                    </ControlTemplate.Triggers>
                </ControlTemplate>
            </Setter.Value>
        </Setter>
    </Style>
    <Style x:Key="Primario" TargetType="Button" BasedOn="{StaticResource {x:Type Button}}">
        <Setter Property="Background" Value="%(blu)s"/>
        <Setter Property="BorderBrush" Value="%(blu)s"/>
        <Setter Property="Foreground" Value="#FFFFFF"/>
        <Setter Property="FontWeight" Value="SemiBold"/>
        <Setter Property="Padding" Value="18,6"/>
        <Setter Property="MinWidth" Value="120"/>
        <Setter Property="Template">
            <Setter.Value>
                <ControlTemplate TargetType="Button">
                    <Border x:Name="bd" Background="{TemplateBinding Background}" CornerRadius="4"
                            Padding="{TemplateBinding Padding}">
                        <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
                    </Border>
                    <ControlTemplate.Triggers>
                        <Trigger Property="IsMouseOver" Value="True">
                            <Setter TargetName="bd" Property="Background" Value="%(blu_scuro)s"/>
                        </Trigger>
                        <Trigger Property="IsEnabled" Value="False">
                            <Setter Property="Opacity" Value="0.45"/>
                        </Trigger>
                    </ControlTemplate.Triggers>
                </ControlTemplate>
            </Setter.Value>
        </Setter>
    </Style>
    <Style TargetType="CheckBox">
        <Setter Property="VerticalContentAlignment" Value="Center"/>
        <Setter Property="Margin" Value="0,3"/>
        <Setter Property="FontSize" Value="12"/>
        <Setter Property="Foreground" Value="%(testo)s"/>
    </Style>
    <Style TargetType="RadioButton">
        <Setter Property="VerticalContentAlignment" Value="Center"/>
        <Setter Property="Margin" Value="0,3"/>
        <Setter Property="FontSize" Value="12"/>
        <Setter Property="Foreground" Value="%(testo)s"/>
    </Style>
    <Style TargetType="TextBox">
        <Setter Property="MinHeight" Value="28"/>
        <Setter Property="Padding" Value="6,0"/>
        <Setter Property="VerticalContentAlignment" Value="Center"/>
        <Setter Property="FontSize" Value="12"/>
        <Setter Property="Foreground" Value="%(testo)s"/>
        <Setter Property="BorderBrush" Value="%(bordo)s"/>
    </Style>
    <Style TargetType="ComboBox">
        <Setter Property="MinHeight" Value="28"/>
        <Setter Property="VerticalContentAlignment" Value="Center"/>
        <Setter Property="FontSize" Value="12"/>
        <Setter Property="Foreground" Value="%(testo)s"/>
    </Style>
    <Style TargetType="Expander">
        <Setter Property="Foreground" Value="%(testo_sec)s"/>
        <Setter Property="FontSize" Value="12"/>
        <Setter Property="FontWeight" Value="SemiBold"/>
        <Setter Property="Margin" Value="0,0,0,10"/>
    </Style>
    <Style x:Key="Intestazione" TargetType="Border">
        <Setter Property="Background" Value="%(blu)s"/>
        <Setter Property="CornerRadius" Value="6"/>
        <Setter Property="Padding" Value="14,10"/>
        <Setter Property="Margin" Value="0,0,0,12"/>
    </Style>
    <Style x:Key="Scheda" TargetType="Border">
        <Setter Property="Background" Value="#FFFFFF"/>
        <Setter Property="BorderBrush" Value="%(bordo_chiaro)s"/>
        <Setter Property="BorderThickness" Value="1"/>
        <Setter Property="CornerRadius" Value="6"/>
        <Setter Property="Padding" Value="12"/>
        <Setter Property="Margin" Value="0,0,0,10"/>
    </Style>
    <Style x:Key="Etichetta" TargetType="TextBlock">
        <Setter Property="FontSize" Value="11"/>
        <Setter Property="FontWeight" Value="Bold"/>
        <Setter Property="Foreground" Value="%(testo_sec)s"/>
        <Setter Property="Margin" Value="0,0,0,6"/>
    </Style>
</Window.Resources>""" % {
    u"btn": u"\n        ".join(_P % kv for kv in [
        (u"Padding", u"12,5"), (u"Margin", u"2"), (u"BorderThickness", u"1"),
        (u"BorderBrush", BORDO), (u"Background", u"#FFFFFF"), (u"Foreground", TESTO),
        (u"FontSize", u"12"), (u"Cursor", u"Hand")]),
    u"hover": AZZURRO_CHIARO, u"blu": BLU, u"blu_scuro": BLU_SCURO, u"azzurro": AZZURRO,
    u"testo": TESTO, u"testo_sec": TESTO_SECONDARIO, u"bordo": BORDO,
    u"bordo_chiaro": BORDO_CHIARO,
})

_RISORSE_VECCHIE = re.compile(r"\s*<Window\.Resources>.*?</Window\.Resources>", re.S)
_APERTURA_WINDOW = re.compile(r"<Window\b[^>]*>", re.S)


def prepara_xaml(testo):
    """Il testo del file ui.xaml con gli stili condivisi al posto di quelli propri."""
    testo = _RISORSE_VECCHIE.sub(u"", testo, count=1)
    m = _APERTURA_WINDOW.search(testo)
    if m is None:
        return testo
    return testo[:m.end()] + u"\n    " + RISORSE + testo[m.end():]


def converti_colori(testo):
    """Sostituisce i colori delle vecchie finestre con quelli della tavolozza."""
    def _sost(m):
        return CONVERSIONE_COLORI.get(m.group(0).upper(), m.group(0))
    return re.sub(u"#[0-9A-Fa-f]{6}\\b", _sost, testo)


def xaml(percorso):
    """Legge ui.xaml e lo restituisce pronto per WPFWindow(..., literal_string=True)."""
    with io.open(percorso, "r", encoding="utf-8-sig") as f:
        return prepara_xaml(f.read())
