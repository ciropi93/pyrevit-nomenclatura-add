using System;
using System.Collections.Generic;
using System.Drawing;
using System.Globalization;
using System.Text.RegularExpressions;

namespace CDVColori
{
    /// <summary>Modalita' della riga varianti.</summary>
    public enum VariantMode
    {
        Luminosita = 0,
        Saturazione = 1,
        Tinta = 2,
        Armonie = 3,
    }

    /// <summary>Insieme di varianti da mostrare in riga.</summary>
    public sealed class VariantSet
    {
        public Color[] Colors;
        public string[] Labels;
        /// <summary>Posizione del colore di partenza.</summary>
        public int BaseIndex;
        /// <summary>Indici da cui inizia un nuovo gruppo (spazio prima del riquadro). Vuoto = riga continua.</summary>
        public int[] GroupStarts = new int[0];
    }

    /// <summary>
    /// Matematica dei colori, senza interfaccia ne' file: parsing, HEX, HSL, Lab, varianti.
    /// (Compilato anche dal progetto di test.)
    /// Accetta #RRGGBB, RRGGBB, #RGB, "R,G,B", "R G B", "RGB 128-128-128".
    /// </summary>
    public static partial class ColorText
    {
        public const int MinPassi = 2, MaxPassi = 6;

        private static readonly Regex HexRe = new Regex(@"^#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$");
        private static readonly Regex RgbRe = new Regex(@"^(?:rgb)?\s*\(?\s*(\d{1,3})\s*[,;\-\s]\s*(\d{1,3})\s*[,;\-\s]\s*(\d{1,3})\s*\)?$",
            RegexOptions.IgnoreCase);

        public static bool TryParse(string text, out Color color)
        {
            color = Color.Black;
            if (string.IsNullOrWhiteSpace(text)) return false;
            string t = text.Trim();

            Match m = HexRe.Match(t);
            if (m.Success)
            {
                string h = m.Groups[1].Value;
                if (h.Length == 3) h = new string(new[] { h[0], h[0], h[1], h[1], h[2], h[2] });
                int v = int.Parse(h, NumberStyles.HexNumber, CultureInfo.InvariantCulture);
                color = Color.FromArgb((v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF);
                return true;
            }

            m = RgbRe.Match(t);
            if (m.Success)
            {
                int r = int.Parse(m.Groups[1].Value, CultureInfo.InvariantCulture);
                int g = int.Parse(m.Groups[2].Value, CultureInfo.InvariantCulture);
                int b = int.Parse(m.Groups[3].Value, CultureInfo.InvariantCulture);
                if (r > 255 || g > 255 || b > 255) return false;
                color = Color.FromArgb(r, g, b);
                return true;
            }
            return false;
        }

        public static string ToHex(Color c)
        {
            return "#" + c.R.ToString("X2") + c.G.ToString("X2") + c.B.ToString("X2");
        }

        public static string ToRgb(Color c)
        {
            return c.R + "-" + c.G + "-" + c.B;
        }

        public static bool SameRgb(Color a, Color b)
        {
            return a.R == b.R && a.G == b.G && a.B == b.B;
        }

        /// <summary>Colore del testo leggibile sopra al colore dato.</summary>
        public static Color Contrast(Color c)
        {
            double l = 0.299 * c.R + 0.587 * c.G + 0.114 * c.B;
            return l > 140 ? Color.Black : Color.White;
        }

        // ------------------------------------------------------------------ varianti

        /// <summary>Compatibilita': varianti di luminosita' [scuri..., colore, chiari...].</summary>
        public static Color[] Variants(Color c, int perLato)
        {
            return Variants(c, VariantMode.Luminosita, perLato).Colors;
        }

        /// <summary>
        /// Varianti del colore secondo la modalita':
        /// Luminosita' = stessa tinta e saturazione, verso nero (sinistra) e bianco (destra);
        /// Saturazione = verso il grigio (sinistra) e verso il colore pieno (destra);
        /// Tinta = rotazione di 10 gradi per passo, in senso antiorario (sinistra) e orario (destra);
        /// Armonie = complementare, analoghi, triade, complementari divisi (passi ignorati).
        /// </summary>
        public static VariantSet Variants(Color c, VariantMode mode, int passi)
        {
            if (passi < MinPassi) passi = MinPassi;
            if (passi > MaxPassi) passi = MaxPassi;
            Color base0 = Color.FromArgb(c.R, c.G, c.B);
            double h, s, l;
            ToHsl(base0, out h, out s, out l);

            if (mode == VariantMode.Armonie) return Harmonies(base0, h, s, l);

            VariantSet vs = new VariantSet();
            vs.Colors = new Color[passi * 2 + 1];
            vs.Labels = new string[passi * 2 + 1];
            vs.BaseIndex = passi;
            vs.Colors[passi] = base0;
            vs.Labels[passi] = "Colore attuale";
            for (int i = 1; i <= passi; i++)
            {
                double f = i / (double)(passi + 1);
                Color lo, hi;
                string loName, hiName;
                switch (mode)
                {
                    case VariantMode.Saturazione:
                        lo = FromHsl(h, s * (1 - f), l);
                        hi = FromHsl(h, s + (1 - s) * f, l);
                        loName = "Meno saturo " + i; hiName = "Più saturo " + i;
                        break;
                    case VariantMode.Tinta:
                        lo = FromHsl(Wrap(h - i * 10.0 / 360), s, l);
                        hi = FromHsl(Wrap(h + i * 10.0 / 360), s, l);
                        loName = "Tinta -" + (i * 10) + "°"; hiName = "Tinta +" + (i * 10) + "°";
                        break;
                    default:
                        lo = FromHsl(h, s, l * (1 - f));
                        hi = FromHsl(h, s, l + (1 - l) * f);
                        loName = "Più scuro " + i; hiName = "Più chiaro " + i;
                        break;
                }
                vs.Colors[passi - i] = lo; vs.Labels[passi - i] = loName;
                vs.Colors[passi + i] = hi; vs.Labels[passi + i] = hiName;
            }
            return vs;
        }

        private static VariantSet Harmonies(Color base0, double h, double s, double l)
        {
            List<Color> cols = new List<Color>();
            List<string> labs = new List<string>();
            List<int> starts = new List<int>();
            Action<string, double[]> group = delegate (string name, double[] gradi)
            {
                starts.Add(cols.Count);
                foreach (double g in gradi)
                {
                    cols.Add(FromHsl(Wrap(h + g / 360.0), s, l));
                    labs.Add(name + (g >= 0 ? " +" : " ") + g + "°");
                }
            };
            cols.Add(base0); labs.Add("Colore attuale");
            group("Complementare", new double[] { 180 });
            group("Analogo", new double[] { -30, 30 });
            group("Triade", new double[] { 120, 240 });
            group("Complementare diviso", new double[] { 150, 210 });
            VariantSet vs = new VariantSet();
            vs.Colors = cols.ToArray();
            vs.Labels = labs.ToArray();
            vs.BaseIndex = 0;
            vs.GroupStarts = starts.ToArray();
            return vs;
        }

        private static double Wrap(double h)
        {
            h = h % 1.0;
            return h < 0 ? h + 1 : h;
        }

        // ------------------------------------------------------------------ HSL

        /// <summary>RGB -> HSL, tutti i valori tra 0 e 1.</summary>
        public static void ToHsl(Color c, out double h, out double s, out double l)
        {
            double r = c.R / 255.0, g = c.G / 255.0, b = c.B / 255.0;
            double max = Math.Max(r, Math.Max(g, b)), min = Math.Min(r, Math.Min(g, b));
            l = (max + min) / 2;
            double d = max - min;
            if (d < 1e-9) { h = 0; s = 0; return; }
            s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
            if (max == r) h = (g - b) / d + (g < b ? 6 : 0);
            else if (max == g) h = (b - r) / d + 2;
            else h = (r - g) / d + 4;
            h /= 6;
        }

        public static Color FromHsl(double h, double s, double l)
        {
            double r, g, b;
            if (s < 1e-9) { r = g = b = l; }
            else
            {
                double q = l < 0.5 ? l * (1 + s) : l + s - l * s;
                double p = 2 * l - q;
                r = HueToRgb(p, q, h + 1.0 / 3);
                g = HueToRgb(p, q, h);
                b = HueToRgb(p, q, h - 1.0 / 3);
            }
            return Color.FromArgb(To255(r), To255(g), To255(b));
        }

        private static double HueToRgb(double p, double q, double t)
        {
            if (t < 0) t += 1;
            if (t > 1) t -= 1;
            if (t < 1.0 / 6) return p + (q - p) * 6 * t;
            if (t < 0.5) return q;
            if (t < 2.0 / 3) return p + (q - p) * (2.0 / 3 - t) * 6;
            return p;
        }

        private static int To255(double v)
        {
            int i = (int)Math.Round(v * 255);
            return i < 0 ? 0 : (i > 255 ? 255 : i);
        }

        // ------------------------------------------------------------------ Lab

        /// <summary>sRGB -> CIE Lab (D65).</summary>
        public static void ToLab(int r, int g, int b, out double L, out double A, out double B)
        {
            double rl = Lin(r), gl = Lin(g), bl = Lin(b);
            double x = (0.4124 * rl + 0.3576 * gl + 0.1805 * bl) / 0.95047;
            double y = (0.2126 * rl + 0.7152 * gl + 0.0722 * bl);
            double z = (0.0193 * rl + 0.1192 * gl + 0.9505 * bl) / 1.08883;
            double fx = F(x), fy = F(y), fz = F(z);
            L = 116 * fy - 16;
            A = 500 * (fx - fy);
            B = 200 * (fy - fz);
        }

        /// <summary>Distanza percettiva semplice (Delta E 1976).</summary>
        public static double DeltaE(Color a, Color b)
        {
            double l1, a1, b1, l2, a2, b2;
            ToLab(a.R, a.G, a.B, out l1, out a1, out b1);
            ToLab(b.R, b.G, b.B, out l2, out a2, out b2);
            return Math.Sqrt((l1 - l2) * (l1 - l2) + (a1 - a2) * (a1 - a2) + (b1 - b2) * (b1 - b2));
        }

        private static double Lin(int v)
        {
            double c = v / 255.0;
            return c <= 0.04045 ? c / 12.92 : Math.Pow((c + 0.055) / 1.055, 2.4);
        }

        private static double F(double t)
        {
            return t > 0.008856 ? Math.Pow(t, 1.0 / 3) : 7.787 * t + 16.0 / 116;
        }
    }
}
