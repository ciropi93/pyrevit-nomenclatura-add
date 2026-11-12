using System.Drawing;
using CDVColori;
using Xunit;

public class ColorMathTests
{
    [Theory]
    [InlineData("#FF8800", 255, 136, 0)]
    [InlineData("ff8800", 255, 136, 0)]
    [InlineData("#F80", 255, 136, 0)]
    [InlineData("255,136,0", 255, 136, 0)]
    [InlineData("255; 136; 0", 255, 136, 0)]
    [InlineData("255 136 0", 255, 136, 0)]
    [InlineData("RGB 128-128-128", 128, 128, 128)]
    [InlineData("rgb(1, 2, 3)", 1, 2, 3)]
    public void Parse_formati_validi(string text, int r, int g, int b)
    {
        Color c;
        Assert.True(ColorText.TryParse(text, out c));
        Assert.Equal(Color.FromArgb(r, g, b).ToArgb(), c.ToArgb());
    }

    [Theory]
    [InlineData("")]
    [InlineData("#GG0000")]
    [InlineData("256,0,0")]
    [InlineData("1,2")]
    public void Parse_formati_non_validi(string text)
    {
        Color c;
        Assert.False(ColorText.TryParse(text, out c));
    }

    [Fact]
    public void Hex_e_rgb()
    {
        Color c = Color.FromArgb(18, 52, 86);
        Assert.Equal("#123456", ColorText.ToHex(c));
        Assert.Equal("18-52-86", ColorText.ToRgb(c));
    }

    [Fact]
    public void Hsl_andata_e_ritorno()
    {
        for (int r = 0; r < 256; r += 17)
            for (int g = 0; g < 256; g += 17)
                for (int b = 0; b < 256; b += 17)
                {
                    double h, s, l;
                    Color c = Color.FromArgb(r, g, b);
                    ColorText.ToHsl(c, out h, out s, out l);
                    Assert.Equal(c.ToArgb(), ColorText.FromHsl(h, s, l).ToArgb());
                }
    }

    [Fact]
    public void Luminosita_dal_rosso()
    {
        VariantSet v = ColorText.Variants(Color.FromArgb(255, 0, 0), VariantMode.Luminosita, 4);
        Assert.Equal(9, v.Colors.Length);
        Assert.Equal(4, v.BaseIndex);
        Assert.Equal("#FF0000", ColorText.ToHex(v.Colors[4]));
        Assert.Equal("#CC0000", ColorText.ToHex(v.Colors[3]));   // l 0.5 -> 0.4
        Assert.Equal("#FF3333", ColorText.ToHex(v.Colors[5]));   // l 0.5 -> 0.6
        for (int i = 1; i < v.Colors.Length; i++)
            Assert.True(Luma(v.Colors[i]) > Luma(v.Colors[i - 1]), "luminosita' crescente");
    }

    [Fact]
    public void Passi_regolabili_e_limitati()
    {
        Color c = Color.FromArgb(100, 150, 200);
        Assert.Equal(5, ColorText.Variants(c, VariantMode.Luminosita, 2).Colors.Length);
        Assert.Equal(13, ColorText.Variants(c, VariantMode.Luminosita, 6).Colors.Length);
        Assert.Equal(13, ColorText.Variants(c, VariantMode.Luminosita, 99).Colors.Length);
        Assert.Equal(5, ColorText.Variants(c, VariantMode.Luminosita, 0).Colors.Length);
    }

    [Fact]
    public void Saturazione_va_dal_grigio_al_pieno()
    {
        Color c = Color.FromArgb(100, 150, 200);
        VariantSet v = ColorText.Variants(c, VariantMode.Saturazione, 3);
        double prev = -1;
        foreach (Color x in v.Colors)
        {
            double h, s, l;
            ColorText.ToHsl(x, out h, out s, out l);
            Assert.True(s >= prev - 0.02, "saturazione crescente");
            prev = s;
        }
    }

    [Fact]
    public void Tinta_ruota_di_10_gradi()
    {
        VariantSet v = ColorText.Variants(Color.FromArgb(255, 0, 0), VariantMode.Tinta, 3);
        double h, s, l;
        ColorText.ToHsl(v.Colors[v.BaseIndex + 3], out h, out s, out l);
        Assert.InRange(h * 360, 28, 32);
        ColorText.ToHsl(v.Colors[v.BaseIndex - 3], out h, out s, out l);
        Assert.InRange(h * 360, 328, 332);
    }

    [Fact]
    public void Armonie_del_rosso()
    {
        VariantSet v = ColorText.Variants(Color.FromArgb(255, 0, 0), VariantMode.Armonie, 4);
        Assert.Equal(0, v.BaseIndex);
        Assert.Equal(8, v.Colors.Length);
        Assert.Equal(new[] { 1, 2, 4, 6 }, v.GroupStarts);
        Assert.Equal("#00FFFF", ColorText.ToHex(v.Colors[1]));   // complementare
        Assert.Equal("#00FF00", ColorText.ToHex(v.Colors[4]));   // triade +120
        Assert.Equal("#0000FF", ColorText.ToHex(v.Colors[5]));   // triade +240
    }

    [Fact]
    public void DeltaE_zero_e_grande()
    {
        Assert.Equal(0, ColorText.DeltaE(Color.Red, Color.Red), 6);
        Assert.True(ColorText.DeltaE(Color.Black, Color.White) > 99);
        Assert.True(ColorText.DeltaE(Color.FromArgb(100, 100, 100), Color.FromArgb(101, 100, 100)) < 1);
    }

    private static double Luma(Color c) { return 0.299 * c.R + 0.587 * c.G + 0.114 * c.B; }
}
