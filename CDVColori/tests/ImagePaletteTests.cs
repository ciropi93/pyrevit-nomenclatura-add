using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Text;
using CDVColori;
using Xunit;
using Xunit.Abstractions;

public class ImagePaletteTests
{
    private readonly ITestOutputHelper output;
    public ImagePaletteTests(ITestOutputHelper output) { this.output = output; }

    private static readonly string[] Attesi =
    {
        "#D4DEBB", "#D79E80", "#AFB8C1", "#E8E7E3", "#D2D6D7", "#BECCD7", "#9DB2C3", "#DBBCB7", "#F2C2AB",
        "#F3D3B8", "#EBDCC7", "#D0D3B4", "#C7D1B8", "#B8C3B5", "#ADC3B7", "#A6BEA4", "#A5A186", "#889C90",
        "#595F53", "#5D6D62", "#7D876E", "#C3C7C8", "#A2A6A9", "#B5C9E0", "#CCD9E9", "#44483E", "#5C615A",
        "#788275", "#697069", "#828E84", "#656751", "#7E8069", "#989A84", "#769863", "#91AC81", "#C9D2C0",
        "#849B8F", "#A0B8AB", "#C2D5CB",
    };

    [Fact]
    public void Immagine_sintetica_con_testo_e_rumore()
    {
        int w = 420, h = 300;
        int[] px = Enumerable.Repeat(unchecked((int)0xFFFFFFFF), w * h).ToArray();
        Color[] cols =
        {
            Color.FromArgb(212, 222, 187), Color.FromArgb(215, 158, 128), Color.FromArgb(175, 184, 193),
            Color.FromArgb(89, 95, 83), Color.FromArgb(118, 152, 99), Color.FromArgb(242, 194, 171),
            Color.FromArgb(30, 60, 160), Color.FromArgb(200, 40, 40), Color.FromArgb(250, 220, 60),
            Color.FromArgb(120, 120, 120), Color.FromArgb(60, 180, 170), Color.FromArgb(150, 90, 200),
        };
        Random rnd = new Random(7);
        for (int k = 0; k < cols.Length; k++)
        {
            int x0 = 10 + (k % 4) * 100, y0 = 10 + (k / 4) * 95;
            for (int y = y0; y < y0 + 85; y++)
                for (int x = x0; x < x0 + 90; x++)
                {
                    Color c = cols[k];
                    bool testo = (y - y0) % 20 < 2 && (x - x0) > 15 && (x - x0) < 70; // righe di "testo"
                    int r = testo ? 20 : c.R + rnd.Next(-2, 3);
                    int g = testo ? 20 : c.G + rnd.Next(-2, 3);
                    int b = testo ? 20 : c.B + rnd.Next(-2, 3);
                    px[y * w + x] = Color.FromArgb(Clamp(r), Clamp(g), Clamp(b)).ToArgb();
                }
        }
        ExtractResult res = ImagePalette.Extract(px, w, h, new ExtractOptions());
        Assert.False(res.UsedFallback);
        Assert.Equal(cols.Length, res.Colors.Count);
        foreach (Color c in cols)
            Assert.Contains(res.Colors, f => MaxDiff(f.Color, c) <= 2);
        Assert.All(res.Colors, f => Assert.NotEmpty(f.Points));
    }

    [Fact]
    public void Diagramma_a_corona_ritrova_la_palette_base()
    {
        int w, h;
        int[] px = LoadPpmGz(Path.Combine(AppContext.BaseDirectory, "data", "corona.ppm.gz"), out w, out h);
        ExtractResult res = ImagePalette.Extract(px, w, h, new ExtractOptions());
        foreach (FoundColor f in res.Colors)
            output.WriteLine(ColorText.ToHex(f.Color) + "  " + f.AreaPercent.ToString("0.0") + "%");
        output.WriteLine("Trovati: " + res.Colors.Count);
        Assert.False(res.UsedFallback);
        int mancanti = 0;
        foreach (string hex in Attesi)
        {
            Color c;
            ColorText.TryParse(hex, out c);
            if (!res.Colors.Any(f => MaxDiff(f.Color, c) <= 4)) { mancanti++; output.WriteLine("manca " + hex); }
        }
        Assert.True(mancanti <= 1, "colori della Base non ritrovati: " + mancanti);
        Assert.InRange(res.Colors.Count, 36, 44);
    }

    [Fact]
    public void Sfumatura_usa_la_quantizzazione()
    {
        int w = 300, h = 200;
        int[] px = new int[w * h];
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++)
                px[y * w + x] = Color.FromArgb(x * 255 / w, y * 255 / h, 128).ToArgb();
        ExtractResult res = ImagePalette.Extract(px, w, h, new ExtractOptions { FallbackColors = 8 });
        Assert.True(res.UsedFallback);
        Assert.InRange(res.Colors.Count, 2, 8);
    }

    [Fact]
    public void Ignora_bianco_e_nero()
    {
        int w = 200, h = 100;
        int[] px = new int[w * h];
        for (int i = 0; i < px.Length; i++)
            px[i] = (i % w < 100 ? Color.Black : Color.FromArgb(40, 120, 200)).ToArgb();
        ExtractResult res = ImagePalette.Extract(px, w, h, new ExtractOptions { IgnoreBlack = true });
        Assert.Single(res.Colors);
        Assert.Equal("#2878C8", ColorText.ToHex(res.Colors[0].Color));
    }

    private static int Clamp(int v) { return v < 0 ? 0 : v > 255 ? 255 : v; }

    private static int MaxDiff(Color a, Color b)
    {
        return Math.Max(Math.Abs(a.R - b.R), Math.Max(Math.Abs(a.G - b.G), Math.Abs(a.B - b.B)));
    }

    private static int[] LoadPpmGz(string path, out int w, out int h)
    {
        using (var gz = new GZipStream(File.OpenRead(path), CompressionMode.Decompress))
        using (var ms = new MemoryStream())
        {
            gz.CopyTo(ms);
            byte[] d = ms.ToArray();
            int pos = 0;
            Func<string> token = () =>
            {
                while (char.IsWhiteSpace((char)d[pos])) pos++;
                var sb = new StringBuilder();
                while (!char.IsWhiteSpace((char)d[pos])) sb.Append((char)d[pos++]);
                return sb.ToString();
            };
            Assert.Equal("P6", token());
            w = int.Parse(token()); h = int.Parse(token()); token();
            pos++;
            int[] px = new int[w * h];
            for (int i = 0; i < px.Length; i++, pos += 3)
                px[i] = Color.FromArgb(d[pos], d[pos + 1], d[pos + 2]).ToArgb();
            return px;
        }
    }
}
