using System;
using System.Diagnostics;
using System.IO;
using System.Text;

namespace CDVColori
{
    /// <summary>
    /// Rapporto sulle finestre di dialogo aperte e sui loro controlli: serve a verificare che la finestra
    /// Colore di Revit abbia i campi standard (ID 706/707/708) e dove stanno i pulsanti.
    /// </summary>
    internal static class Diagnosi
    {
        public static string Run(Settings settings)
        {
            StringBuilder sb = new StringBuilder();
            sb.AppendLine("CDV Colori - diagnosi " + DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"));
            sb.AppendLine("Windows: " + Environment.OSVersion + (Environment.Is64BitOperatingSystem ? " 64 bit" : " 32 bit"));
            sb.AppendLine("Processo a 64 bit: " + Environment.Is64BitProcess);
            sb.AppendLine("Programmi seguiti: " + string.Join(", ", settings.programmi.ToArray()));
            sb.AppendLine("Cartella palette: " + settings.PaletteDir);
            sb.AppendLine();

            int count = 0;
            Native.EnumWindows(delegate (IntPtr h, IntPtr l)
            {
                if (!Native.IsWindowVisible(h) || Native.ClassName(h) != "#32770") return true;
                uint pid;
                Native.GetWindowThreadProcessId(h, out pid);
                if (pid == (uint)Process.GetCurrentProcess().Id) return true;
                string pname = "?";
                try { pname = Process.GetProcessById((int)pid).ProcessName; } catch { }
                count++;
                ColorDialogTarget t = ColorDialogTarget.TryCreate(h, null);
                sb.AppendLine("=== Finestra \"" + Native.WindowText(h) + "\"  processo " + pname + " (" + pid + ")");
                sb.AppendLine("    rettangolo " + Native.WindowRect(h) + "  scala " + Native.ScaleForWindow(h));
                sb.AppendLine("    finestra Colore standard riconosciuta: " + (t != null ? "SI" : "NO"));
                if (t != null)
                {
                    System.Drawing.Color? c = t.ReadRgb();
                    sb.AppendLine("    colore letto: " + (c.HasValue ? ColorText.ToHex(c.Value) + " / RGB " + ColorText.ToRgb(c.Value) : "(non leggibile)"));
                    sb.AppendLine("    seguita da CDV Colori: " + (ColorDialogTarget.TryCreate(h, settings) != null ? "SI" : "NO (programma non in elenco)"));
                }
                sb.AppendLine("    controlli:  ID | classe | testo | rettangolo | visibile");
                Native.EnumChildWindows(h, delegate (IntPtr c, IntPtr l2)
                {
                    string text = Native.WindowText(c);
                    if (text.Length == 0 && Native.ClassName(c).IndexOf("Edit", StringComparison.OrdinalIgnoreCase) >= 0)
                        text = Native.ControlText(c) ?? "";
                    sb.AppendLine("      " + Native.GetDlgCtrlID(c) + " | " + Native.ClassName(c) + " | \"" +
                        text.Replace("\r", " ").Replace("\n", " ") + "\" | " + Native.WindowRect(c) + " | " +
                        (Native.IsWindowVisible(c) ? "si" : "no"));
                    return true;
                }, IntPtr.Zero);
                sb.AppendLine();
                return true;
            }, IntPtr.Zero);

            if (count == 0)
                sb.AppendLine("Nessuna finestra di dialogo aperta. Apri la finestra Colore in Revit e ripeti la diagnosi.");

            string path = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),
                "CDVColori_diagnosi.txt");
            try { File.WriteAllText(path, sb.ToString(), new UTF8Encoding(true)); }
            catch
            {
                path = Path.Combine(Settings.AppDataDir, "CDVColori_diagnosi.txt");
                File.WriteAllText(path, sb.ToString(), new UTF8Encoding(true));
            }
            return path;
        }
    }
}
