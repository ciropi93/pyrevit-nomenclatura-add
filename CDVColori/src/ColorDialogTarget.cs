using System;
using System.Diagnostics;
using System.Drawing;
using System.Globalization;

namespace CDVColori
{
    /// <summary>
    /// Una finestra "Colore" aperta (la finestra standard di Windows, che Revit usa con qualche aggiunta).
    /// Si legge e si scrive solo attraverso i suoi campi Rosso/Verde/Blu, come farebbe l'utente.
    /// </summary>
    public class ColorDialogTarget
    {
        // ID standard della finestra colori di Windows (colordlg.h)
        public const int ID_HUE = 703, ID_SAT = 704, ID_LUM = 705;
        public const int ID_RED = 706, ID_GREEN = 707, ID_BLUE = 708;
        public const int ID_ADD = 712;

        public IntPtr Hwnd { get; private set; }
        public uint ProcessId { get; private set; }
        public uint ThreadId { get; private set; }
        public string ProcessName { get; private set; }

        private IntPtr edRed, edGreen, edBlue;

        /// <summary>Restituisce il bersaglio se hwnd e' una finestra colori di uno dei programmi indicati, altrimenti null.</summary>
        public static ColorDialogTarget TryCreate(IntPtr hwnd, Settings settings)
        {
            if (hwnd == IntPtr.Zero || !Native.IsWindow(hwnd)) return null;
            if (!Native.IsTopLevel(hwnd)) return null;
            if (Native.ClassName(hwnd) != "#32770") return null;

            IntPtr r = Native.GetDlgItem(hwnd, ID_RED);
            IntPtr g = Native.GetDlgItem(hwnd, ID_GREEN);
            IntPtr b = Native.GetDlgItem(hwnd, ID_BLUE);
            if (r == IntPtr.Zero || g == IntPtr.Zero || b == IntPtr.Zero) return null;
            if (!IsEdit(r) || !IsEdit(g) || !IsEdit(b)) return null;

            uint pid;
            uint tid = Native.GetWindowThreadProcessId(hwnd, out pid);
            if (pid == (uint)Process.GetCurrentProcess().Id) return null;

            string pname = "";
            try { pname = Process.GetProcessById((int)pid).ProcessName; } catch { }
            if (settings != null && !ProcessAllowed(pname, settings)) return null;

            ColorDialogTarget t = new ColorDialogTarget();
            t.Hwnd = hwnd;
            t.ProcessId = pid;
            t.ThreadId = tid;
            t.ProcessName = pname;
            t.edRed = r; t.edGreen = g; t.edBlue = b;
            return t;
        }

        private static bool IsEdit(IntPtr h)
        {
            return Native.ClassName(h).IndexOf("Edit", StringComparison.OrdinalIgnoreCase) >= 0;
        }

        private static bool ProcessAllowed(string pname, Settings s)
        {
            foreach (string p in s.programmi)
            {
                if (p == "*") return true;
                string n = p.EndsWith(".exe", StringComparison.OrdinalIgnoreCase) ? p.Substring(0, p.Length - 4) : p;
                if (string.Equals(n, pname, StringComparison.OrdinalIgnoreCase)) return true;
            }
            return false;
        }

        public bool IsAlive { get { return Native.IsWindow(Hwnd) && Native.IsWindowVisible(Hwnd); } }

        public Rectangle Bounds { get { return Native.WindowRect(Hwnd); } }

        public float Scale { get { return Native.ScaleForWindow(Hwnd); } }

        /// <summary>Rettangolo (schermo) di un controllo della finestra, vuoto se non esiste.</summary>
        public Rectangle ControlRect(int id)
        {
            IntPtr h = Native.GetDlgItem(Hwnd, id);
            if (h == IntPtr.Zero || !Native.IsWindowVisible(h)) return Rectangle.Empty;
            return Native.WindowRect(h);
        }

        /// <summary>Colore attualmente scritto nei campi Rosso/Verde/Blu.</summary>
        public Color? ReadRgb()
        {
            int r, g, b;
            if (!ReadInt(edRed, out r) || !ReadInt(edGreen, out g) || !ReadInt(edBlue, out b)) return null;
            return Color.FromArgb(Clamp(r), Clamp(g), Clamp(b));
        }

        private static bool ReadInt(IntPtr h, out int v)
        {
            v = 0;
            string s = Native.ControlText(h);
            return s != null && int.TryParse(s.Trim(), NumberStyles.Integer, CultureInfo.InvariantCulture, out v);
        }

        private static int Clamp(int v) { return v < 0 ? 0 : (v > 255 ? 255 : v); }

        /// <summary>
        /// Imposta il colore nella finestra Colore.
        /// 1) messaggio standard "commdlg_SetRGBColor": la finestra aggiorna colore, campi e anteprima;
        /// 2) scrive comunque i valori nei campi R/G/B, come se l'utente li digitasse, cosi' anche le
        ///    aggiunte di Autodesk (es. "Nome: RGB ...") vengono aggiornate.
        /// </summary>
        public bool SetRgb(Color c)
        {
            int msg = Native.RegisterWindowMessage("commdlg_SetRGBColor");
            int colorref = c.R | (c.G << 8) | (c.B << 16);
            IntPtr res;
            IntPtr sent = Native.SendMessageTimeout(Hwnd, msg, IntPtr.Zero, new IntPtr(colorref),
                Native.SMTO_ABORTIFHUNG, 1000, out res);
            Color? now = ReadRgb();
            bool viaMessage = sent != IntPtr.Zero && now.HasValue && Same(now.Value, c);

            bool r = Native.SetControlText(edRed, c.R.ToString(CultureInfo.InvariantCulture));
            bool g = Native.SetControlText(edGreen, c.G.ToString(CultureInfo.InvariantCulture));
            bool b = Native.SetControlText(edBlue, c.B.ToString(CultureInfo.InvariantCulture));
            now = ReadRgb();
            bool viaFields = r && g && b && now.HasValue && Same(now.Value, c);

            if (!viaMessage) Log.Write("commdlg_SetRGBColor non gestito; campi R/G/B scritti: " + viaFields);
            return viaMessage || viaFields;
        }

        private static bool Same(Color a, Color b) { return a.R == b.R && a.G == b.G && a.B == b.B; }

        /// <summary>Preme OK nella finestra colori.</summary>
        public void PressOk()
        {
            IntPtr ok = Native.GetDlgItem(Hwnd, Native.IDOK);
            Native.PostMessage(Hwnd, Native.WM_COMMAND, new IntPtr(Native.IDOK), ok);
        }
    }
}
