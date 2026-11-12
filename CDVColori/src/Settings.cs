using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Web.Script.Serialization;

namespace CDVColori
{
    /// <summary>Registro semplice in %APPDATA%\CDVColori\log.txt (utile per la diagnosi).</summary>
    internal static class Log
    {
        public static void Write(string msg)
        {
            try
            {
                string path = Path.Combine(Settings.AppDataDir, "log.txt");
                FileInfo fi = new FileInfo(path);
                if (fi.Exists && fi.Length > 512 * 1024) fi.Delete();
                File.AppendAllText(path, DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + "  " + msg + Environment.NewLine,
                    Encoding.UTF8);
            }
            catch { }
        }
    }

    /// <summary>Impostazioni in %APPDATA%\CDVColori\config.json (modificabile a mano).</summary>
    public class Settings
    {
        // Nomi in minuscolo/italiano: sono le chiavi del file JSON.
        /// <summary>Cartella delle palette. Vuoto = %APPDATA%\CDVColori\palette. Puo' essere una cartella di rete condivisa.</summary>
        public string cartellaPalette { get; set; }
        /// <summary>Programmi in cui agganciarsi (nome del processo senza .exe).</summary>
        public List<string> programmi { get; set; }
        public bool attivo { get; set; }
        public bool mostraPannello { get; set; }
        public bool mostraContagocce { get; set; }
        public string ultimaPalette { get; set; }

        public Settings()
        {
            cartellaPalette = "";
            programmi = new List<string> { "Revit" };
            attivo = true;
            mostraPannello = true;
            mostraContagocce = true;
            ultimaPalette = "";
        }

        public static string AppDataDir
        {
            get
            {
                string dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "CDVColori");
                Directory.CreateDirectory(dir);
                return dir;
            }
        }

        public static string FilePath { get { return Path.Combine(AppDataDir, "config.json"); } }

        public string PaletteDir
        {
            get
            {
                string dir = string.IsNullOrWhiteSpace(cartellaPalette)
                    ? Path.Combine(AppDataDir, "palette")
                    : Environment.ExpandEnvironmentVariables(cartellaPalette.Trim());
                try { Directory.CreateDirectory(dir); } catch (Exception ex) { Log.Write("Cartella palette: " + ex.Message); }
                return dir;
            }
        }

        public static Settings Load()
        {
            try
            {
                if (File.Exists(FilePath))
                {
                    Settings s = new JavaScriptSerializer().Deserialize<Settings>(File.ReadAllText(FilePath, Encoding.UTF8));
                    if (s != null)
                    {
                        if (s.programmi == null || s.programmi.Count == 0) s.programmi = new List<string> { "Revit" };
                        if (s.cartellaPalette == null) s.cartellaPalette = "";
                        return s;
                    }
                }
            }
            catch (Exception ex) { Log.Write("config.json non leggibile: " + ex.Message); }
            Settings def = new Settings();
            def.Save();
            return def;
        }

        public void Save()
        {
            try
            {
                StringBuilder sb = new StringBuilder();
                sb.Append("{\n");
                sb.Append("  \"cartellaPalette\": ").Append(Json.Str(cartellaPalette)).Append(",\n");
                sb.Append("  \"programmi\": [");
                for (int i = 0; i < programmi.Count; i++)
                {
                    if (i > 0) sb.Append(", ");
                    sb.Append(Json.Str(programmi[i]));
                }
                sb.Append("],\n");
                sb.Append("  \"attivo\": ").Append(attivo ? "true" : "false").Append(",\n");
                sb.Append("  \"mostraPannello\": ").Append(mostraPannello ? "true" : "false").Append(",\n");
                sb.Append("  \"mostraContagocce\": ").Append(mostraContagocce ? "true" : "false").Append(",\n");
                sb.Append("  \"ultimaPalette\": ").Append(Json.Str(ultimaPalette)).Append("\n");
                sb.Append("}\n");
                File.WriteAllText(FilePath, sb.ToString(), new UTF8Encoding(false));
            }
            catch (Exception ex) { Log.Write("Salvataggio config: " + ex.Message); }
        }
    }

    internal static class Json
    {
        public static string Str(string s)
        {
            if (s == null) return "\"\"";
            StringBuilder sb = new StringBuilder("\"");
            foreach (char c in s)
            {
                switch (c)
                {
                    case '"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    default:
                        if (c < 0x20) sb.Append("\\u").Append(((int)c).ToString("x4"));
                        else sb.Append(c);
                        break;
                }
            }
            return sb.Append('"').ToString();
        }
    }
}
