using System;
using System.Collections.Generic;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using System.Web.Script.Serialization;

namespace CDVColori
{
    /// <summary>Una voce di palette, cosi' come sta nel file JSON.</summary>
    public class VoceColore
    {
        public string nome { get; set; }
        public string hex { get; set; }

        public VoceColore() { nome = ""; hex = "#000000"; }

        public VoceColore(string nome, Color c)
        {
            this.nome = nome ?? "";
            hex = ColorText.ToHex(c);
        }

        public Color ToColor()
        {
            Color c;
            return ColorText.TryParse(hex, out c) ? c : Color.Black;
        }
    }

    /// <summary>Formato file: {"nome": "...", "colori": [{"nome": "...", "hex": "#RRGGBB"}]}</summary>
    public class FilePalette
    {
        public string nome { get; set; }
        public List<VoceColore> colori { get; set; }
    }

    public class Palette
    {
        public string Nome;
        public List<VoceColore> Colori = new List<VoceColore>();
        public string FilePath;
        public bool IsRecent;

        public override string ToString() { return Nome; }

        public static Palette Load(string path)
        {
            FilePalette fp = new JavaScriptSerializer().Deserialize<FilePalette>(File.ReadAllText(path, Encoding.UTF8));
            Palette p = new Palette();
            p.FilePath = path;
            p.Nome = (fp != null && !string.IsNullOrWhiteSpace(fp.nome)) ? fp.nome : Path.GetFileNameWithoutExtension(path);
            if (fp != null && fp.colori != null)
            {
                foreach (VoceColore v in fp.colori)
                {
                    Color c;
                    if (v != null && ColorText.TryParse(v.hex, out c))
                    {
                        v.hex = ColorText.ToHex(c);
                        if (v.nome == null) v.nome = "";
                        p.Colori.Add(v);
                    }
                }
            }
            return p;
        }

        public void Save()
        {
            StringBuilder sb = new StringBuilder();
            sb.Append("{\n  \"nome\": ").Append(Json.Str(Nome)).Append(",\n  \"colori\": [");
            for (int i = 0; i < Colori.Count; i++)
            {
                sb.Append(i == 0 ? "\n" : ",\n");
                sb.Append("    {\"nome\": ").Append(Json.Str(Colori[i].nome))
                  .Append(", \"hex\": ").Append(Json.Str(Colori[i].hex)).Append("}");
            }
            sb.Append(Colori.Count > 0 ? "\n  ]\n}\n" : "]\n}\n");
            File.WriteAllText(FilePath, sb.ToString(), new UTF8Encoding(false));
        }
    }

    /// <summary>Gestione delle palette su disco.</summary>
    public static class PaletteStore
    {
        public const int MaxRecenti = 32;

        public static string RecentiPath { get { return Path.Combine(Settings.AppDataDir, "recenti.json"); } }

        /// <summary>Recenti (personali) + tutte le palette *.json della cartella.</summary>
        public static List<Palette> LoadAll(string dir)
        {
            List<Palette> list = new List<Palette>();
            list.Add(LoadRecenti());
            try
            {
                string[] files = Directory.GetFiles(dir, "*.json");
                if (files.Length == 0)
                {
                    CreaEsempio(dir);
                    files = Directory.GetFiles(dir, "*.json");
                }
                Array.Sort(files, StringComparer.CurrentCultureIgnoreCase);
                foreach (string f in files)
                {
                    try { list.Add(Palette.Load(f)); }
                    catch (Exception ex) { Log.Write("Palette non leggibile " + f + ": " + ex.Message); }
                }
            }
            catch (Exception ex) { Log.Write("Lettura cartella palette: " + ex.Message); }
            return list;
        }

        public static Palette LoadRecenti()
        {
            Palette p = null;
            try { if (File.Exists(RecentiPath)) p = Palette.Load(RecentiPath); }
            catch (Exception ex) { Log.Write("recenti.json: " + ex.Message); }
            if (p == null) p = new Palette();
            p.Nome = "Recenti";
            p.FilePath = RecentiPath;
            p.IsRecent = true;
            return p;
        }

        public static void AddRecent(Palette recenti, Color c)
        {
            string hex = ColorText.ToHex(c);
            recenti.Colori.RemoveAll(v => string.Equals(v.hex, hex, StringComparison.OrdinalIgnoreCase));
            recenti.Colori.Insert(0, new VoceColore("", c));
            while (recenti.Colori.Count > MaxRecenti) recenti.Colori.RemoveAt(recenti.Colori.Count - 1);
            try { recenti.Save(); } catch (Exception ex) { Log.Write("Salvataggio recenti: " + ex.Message); }
        }

        public static Palette Create(string dir, string nome)
        {
            string baseName = SafeFileName(nome);
            string path = Path.Combine(dir, baseName + ".json");
            int i = 2;
            while (File.Exists(path)) path = Path.Combine(dir, baseName + " (" + (i++) + ").json");
            Palette p = new Palette();
            p.Nome = nome;
            p.FilePath = path;
            p.Save();
            return p;
        }

        public static string SafeFileName(string nome)
        {
            string s = nome ?? "";
            foreach (char c in Path.GetInvalidFileNameChars()) s = s.Replace(c, '_');
            s = s.Trim();
            return s.Length == 0 ? "Palette" : s;
        }

        private static void CreaEsempio(string dir)
        {
            Palette p = new Palette();
            p.Nome = "Esempio";
            p.FilePath = Path.Combine(dir, "Esempio.json");
            string[,] voci =
            {
                { "Nero", "#000000" }, { "Grigio 25%", "#404040" }, { "Grigio 50%", "#808080" },
                { "Grigio 75%", "#C0C0C0" }, { "Bianco", "#FFFFFF" },
                { "Rosso", "#FF0000" }, { "Giallo", "#FFFF00" }, { "Verde", "#00FF00" },
                { "Ciano", "#00FFFF" }, { "Blu", "#0000FF" }, { "Magenta", "#FF00FF" },
            };
            for (int i = 0; i < voci.GetLength(0); i++)
            {
                Color c;
                ColorText.TryParse(voci[i, 1], out c);
                p.Colori.Add(new VoceColore(voci[i, 0], c));
            }
            try { p.Save(); } catch (Exception ex) { Log.Write("Creazione palette di esempio: " + ex.Message); }
        }
    }

    /// <summary>Conversione colore &lt;-&gt; testo. Accetta #RRGGBB, RRGGBB, #RGB, "R,G,B", "R G B", "RGB 128-128-128".</summary>
    public static class ColorText
    {
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

        public static string Describe(VoceColore v)
        {
            Color c = v.ToColor();
            string head = string.IsNullOrWhiteSpace(v.nome) ? "" : v.nome + "\n";
            return head + "RGB " + ToRgb(c) + "   " + ToHex(c);
        }

        /// <summary>Colore del testo leggibile sopra al colore dato.</summary>
        public static Color Contrast(Color c)
        {
            double l = 0.299 * c.R + 0.587 * c.G + 0.114 * c.B;
            return l > 140 ? Color.Black : Color.White;
        }
    }
}
