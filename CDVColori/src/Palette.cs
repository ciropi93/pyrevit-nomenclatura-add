using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Text;
using System.Web.Script.Serialization;

namespace CDVColori
{
    /// <summary>Una voce di palette, cosi' come sta nel file JSON.</summary>
    public class VoceColore
    {
        public string nome { get; set; }
        public string hex { get; set; }
        /// <summary>Gruppo facoltativo (es. "Anello interno"); vuoto = nessun gruppo.</summary>
        public string gruppo { get; set; }

        public VoceColore() { nome = ""; hex = "#000000"; gruppo = ""; }

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

        public bool HasGroups { get { return Colori.Exists(v => !string.IsNullOrEmpty(v.gruppo)); } }

        /// <summary>
        /// Colori raggruppati nell'ordine in cui i gruppi compaiono (i colori senza gruppo vanno in fondo, "Altri").
        /// </summary>
        public List<KeyValuePair<string, List<VoceColore>>> Grouped()
        {
            List<KeyValuePair<string, List<VoceColore>>> res = new List<KeyValuePair<string, List<VoceColore>>>();
            List<VoceColore> senza = new List<VoceColore>();
            foreach (VoceColore v in Colori)
            {
                if (string.IsNullOrEmpty(v.gruppo)) { senza.Add(v); continue; }
                int i = res.FindIndex(kv => kv.Key == v.gruppo);
                if (i < 0) { res.Add(new KeyValuePair<string, List<VoceColore>>(v.gruppo, new List<VoceColore>())); i = res.Count - 1; }
                res[i].Value.Add(v);
            }
            if (senza.Count > 0) res.Add(new KeyValuePair<string, List<VoceColore>>("", senza));
            return res;
        }

        /// <summary>Riordina l'elenco come viene mostrato (gruppi contigui).</summary>
        public void Normalize()
        {
            List<VoceColore> flat = new List<VoceColore>();
            foreach (KeyValuePair<string, List<VoceColore>> kv in Grouped()) flat.AddRange(kv.Value);
            Colori = flat;
        }

        public List<string> GroupNames()
        {
            List<string> res = new List<string>();
            foreach (KeyValuePair<string, List<VoceColore>> kv in Grouped()) if (kv.Key != "") res.Add(kv.Key);
            return res;
        }

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
                        if (v.gruppo == null) v.gruppo = "";
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
                  .Append(", \"hex\": ").Append(Json.Str(Colori[i].hex));
                if (!string.IsNullOrEmpty(Colori[i].gruppo))
                    sb.Append(", \"gruppo\": ").Append(Json.Str(Colori[i].gruppo));
                sb.Append("}");
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
                EnsureBase(dir);
                string[] files = Directory.GetFiles(dir, "*.json");
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

        public const string BaseFile = "Base.json";
        private const string BaseMarker = ".base_creata";

        /// <summary>
        /// Colori della palette di base (estratti dal diagramma a corona "Materialen / Energie /
        /// Klimaatadaptatie / Stikstof"; valori letti da un'immagine JPEG, quindi approssimati di 1-3 unita').
        /// Ordine: anello interno, anello medio, anello esterno.
        /// </summary>
        private static readonly string[,] BaseColori =
        {
            // anello interno
            { "Materialen", "#D4DEBB", "Anello interno" },
            { "Energie", "#D79E80", "Anello interno" },
            { "Klimaatadaptatie", "#AFB8C1", "Anello interno" },
            { "Stikstof", "#E8E7E3", "Anello interno" },
            // anello medio
            { "Stikstof (medio)", "#D2D6D7", "Anello medio" },
            { "Hittestress", "#BECCD7", "Anello medio" },
            { "Waterverwerking", "#9DB2C3", "Anello medio" },
            { "Energiegebruik", "#DBBCB7", "Anello medio" },
            { "Maximale energiebehoefte", "#F2C2AB", "Anello medio" },
            { "Aandeel hernieuwbare energie", "#F3D3B8", "Anello medio" },
            { "Opslag", "#EBDCC7", "Anello medio" },
            { "Milieu-impact", "#D0D3B4", "Anello medio" },
            { "Embodied Carbon", "#C7D1B8", "Anello medio" },
            { "Construction Stored Carbon", "#B8C3B5", "Anello medio" },
            { "Materiaalgebruik", "#ADC3B7", "Anello medio" },
            { "Hergebruikpotentie", "#A6BEA4", "Anello medio" },
            { "Losmaakbaarheid", "#A5A186", "Anello medio" },
            { "Aanpasbaarheid functie", "#889C90", "Anello medio" },
            { "Materialen scuro medio 1", "#595F53", "Anello medio" },
            { "Materialen scuro medio 2 (anche esterno 5)", "#5D6D62", "Anello medio" },
            { "Materialen scuro medio 3", "#7D876E", "Anello medio" },
            // anello esterno
            { "Ammoniak", "#C3C7C8", "Anello esterno" },
            { "Stikstofoxide", "#A2A6A9", "Anello esterno" },
            { "Reductie drinkwaterverbruik", "#B5C9E0", "Anello esterno" },
            { "Gebruik regen- en grijswater", "#CCD9E9", "Anello esterno" },
            { "Materialen scuro esterno 1", "#44483E", "Anello esterno" },
            { "Materialen scuro esterno 2", "#5C615A", "Anello esterno" },
            { "Materialen scuro esterno 3", "#788275", "Anello esterno" },
            { "Materialen scuro esterno 4", "#697069", "Anello esterno" },
            { "Materialen scuro esterno 6", "#828E84", "Anello esterno" },
            { "Materialen scuro esterno 7", "#656751", "Anello esterno" },
            { "Materialen scuro esterno 8", "#7E8069", "Anello esterno" },
            { "Hernieuwbaar", "#989A84", "Anello esterno" },
            { "Hergebruik esterno (verde)", "#769863", "Anello esterno" },
            { "Recyclebaar", "#91AC81", "Anello esterno" },
            { "Herbruikbaar", "#C9D2C0", "Anello esterno" },
            { "Primair grondstof", "#849B8F", "Anello esterno" },
            { "Secundair grondstof", "#A0B8AB", "Anello esterno" },
            { "Hernieuwbaar grondstof", "#C2D5CB", "Anello esterno" },
        };

        /// <summary>
        /// Crea la palette di base la prima volta. Se poi l'utente la elimina non ricompare
        /// (si ripristina dal menu del pannello).
        /// </summary>
        private static void EnsureBase(string dir)
        {
            string marker = Path.Combine(dir, BaseMarker);
            if (File.Exists(marker) || File.Exists(Path.Combine(dir, BaseFile))) return;
            try
            {
                CreaBase(dir);
                File.WriteAllText(marker, "palette di base creata " + DateTime.Now.ToString("s"));
                try { File.SetAttributes(marker, FileAttributes.Hidden); } catch { }
            }
            catch (Exception ex) { Log.Write("Creazione palette di base: " + ex.Message); }
        }

        /// <summary>Scrive (o riscrive) la palette di base.</summary>
        public static Palette CreaBase(string dir)
        {
            Palette p = new Palette();
            p.Nome = "Base";
            p.FilePath = Path.Combine(dir, BaseFile);
            for (int i = 0; i < BaseColori.GetLength(0); i++)
            {
                Color c;
                ColorText.TryParse(BaseColori[i, 1], out c);
                VoceColore v = new VoceColore(BaseColori[i, 0], c);
                v.gruppo = BaseColori[i, 2];
                p.Colori.Add(v);
            }
            p.Save();
            return p;
        }
    }

    /// <summary>Parte di ColorText legata alle palette (il resto e' in ColorMath.cs).</summary>
    public static partial class ColorText
    {
        public static string Describe(VoceColore v)
        {
            Color c = v.ToColor();
            string head = string.IsNullOrWhiteSpace(v.nome) ? "" : v.nome + "\n";
            return head + "RGB " + ToRgb(c) + "   " + ToHex(c);
        }
    }
}
