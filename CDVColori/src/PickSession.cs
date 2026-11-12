using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace CDVColori
{
    /// <summary>
    /// Contagocce: lente vicino al cursore; il clic sinistro prende il colore sotto il cursore, ovunque sullo schermo.
    ///   clic            prende il colore e termina
    ///   Maiusc+clic     prende il colore (va nei Recenti) e continua
    ///   Invio           come il clic, nel punto attuale
    ///   frecce          spostano il cursore di 1 pixel
    ///   rotellina       zoom della lente
    ///   1 / 3 / 5       area di campionamento 1x1, 3x3, 5x5 (media dei pixel)
    ///   clic destro/Esc annulla
    /// Aggancio al mouse e tasti restano attivi solo durante la scelta.
    /// </summary>
    public sealed class PickSession : IDisposable
    {
        private const int IdEsc = 0xCD01, IdEnter = 0xCD02, IdLeft = 0xCD03, IdUp = 0xCD04, IdRight = 0xCD05,
            IdDown = 0xCD06, Id1 = 0xCD07, Id3 = 0xCD08, Id5 = 0xCD09;

        private readonly Settings settings;
        private readonly Action<Color> onPicked;
        private readonly Action<Color> onCollected;
        private readonly Action onEnd;
        private readonly Native.LowLevelMouseProc mouseProc;
        private IntPtr mouseHook = IntPtr.Zero;
        private readonly MagnifierForm lens;
        private readonly Timer timer;
        private bool swallowUp;
        private bool finished;
        private int collected;

        public static PickSession Active { get; private set; }

        private PickSession(Settings settings, Action<Color> onPicked, Action<Color> onCollected, Action onEnd)
        {
            this.settings = settings;
            this.onPicked = onPicked;
            this.onCollected = onCollected;
            this.onEnd = onEnd;
            mouseProc = MouseHookProc;
            lens = new MagnifierForm(settings.contagocceZoom, settings.contagocceArea);
            lens.HotkeyPressed += OnHotkey;
            timer = new Timer();
            timer.Interval = 30;
            timer.Tick += delegate { UpdateLens(); };
        }

        /// <summary>
        /// Avvia la scelta. onPicked: colore scelto (fine). onCollected: colore preso con Maiusc+clic (si continua),
        /// puo' essere null. onEnd: chiamato sempre alla fine.
        /// </summary>
        public static void Start(Settings settings, Action<Color> onPicked, Action<Color> onCollected, Action onEnd)
        {
            if (Active != null) return;
            PickSession s = new PickSession(settings, onPicked, onCollected, onEnd);
            Active = s;
            s.Begin();
        }

        private void Begin()
        {
            UpdateLens();
            lens.ShowNoActivate();
            IntPtr h = lens.Handle;
            Native.RegisterHotKey(h, IdEsc, 0, Native.VK_ESCAPE);
            Native.RegisterHotKey(h, IdEnter, 0, Native.VK_RETURN);
            Native.RegisterHotKey(h, IdLeft, 0, Native.VK_LEFT);
            Native.RegisterHotKey(h, IdUp, 0, Native.VK_UP);
            Native.RegisterHotKey(h, IdRight, 0, Native.VK_RIGHT);
            Native.RegisterHotKey(h, IdDown, 0, Native.VK_DOWN);
            Native.RegisterHotKey(h, Id1, 0, (uint)'1');
            Native.RegisterHotKey(h, Id3, 0, (uint)'3');
            Native.RegisterHotKey(h, Id5, 0, (uint)'5');
            mouseHook = Native.SetWindowsHookEx(Native.WH_MOUSE_LL, mouseProc, Native.GetModuleHandle(null), 0);
            if (mouseHook == IntPtr.Zero)
            {
                Log.Write("Aggancio mouse non riuscito: " + Marshal.GetLastWin32Error());
                Finish(null);
                return;
            }
            timer.Start();
        }

        private void UnregisterKeys()
        {
            IntPtr h = lens.Handle;
            foreach (int id in new[] { IdEsc, IdEnter, IdLeft, IdUp, IdRight, IdDown, Id1, Id3, Id5 })
                Native.UnregisterHotKey(h, id);
        }

        private void OnHotkey(int id)
        {
            if (finished) return;
            Native.POINT p;
            Native.GetCursorPos(out p);
            switch (id)
            {
                case IdEsc: Finish(null); return;
                case IdEnter: Finish(lens.SampleAt(p.X, p.Y)); return;
                case IdLeft: Native.SetCursorPos(p.X - 1, p.Y); break;
                case IdRight: Native.SetCursorPos(p.X + 1, p.Y); break;
                case IdUp: Native.SetCursorPos(p.X, p.Y - 1); break;
                case IdDown: Native.SetCursorPos(p.X, p.Y + 1); break;
                case Id1: SetArea(1); break;
                case Id3: SetArea(3); break;
                case Id5: SetArea(5); break;
            }
            UpdateLens();
        }

        private void SetArea(int a)
        {
            settings.contagocceArea = a;
            settings.Save();
            lens.Area = a;
        }

        private void ChangeZoom(int delta)
        {
            int z = settings.contagocceZoom + (delta > 0 ? 1 : -1) * (settings.contagocceZoom >= 10 ? 2 : 1);
            if (z < 4) z = 4;
            if (z > 20) z = 20;
            if (z == settings.contagocceZoom) return;
            settings.contagocceZoom = z;
            settings.Save();
            lens.Zoom = z;
            UpdateLens();
        }

        private IntPtr MouseHookProc(int nCode, IntPtr wParam, IntPtr lParam)
        {
            if (nCode >= 0 && !finished)
            {
                int msg = wParam.ToInt32();
                Native.MSLLHOOKSTRUCT info = default(Native.MSLLHOOKSTRUCT);
                if (msg == Native.WM_LBUTTONDOWN || msg == Native.WM_MOUSEWHEEL)
                    info = (Native.MSLLHOOKSTRUCT)Marshal.PtrToStructure(lParam, typeof(Native.MSLLHOOKSTRUCT));
                if (msg == Native.WM_LBUTTONDOWN)
                {
                    int x = info.pt.X, y = info.pt.Y;
                    bool more = Native.IsShiftDown() && onCollected != null;
                    swallowUp = true;
                    // il lavoro vero va fuori dall'aggancio, che deve rispondere subito
                    if (more) lens.BeginInvoke((Action)delegate { Collect(lens.SampleAt(x, y)); });
                    else lens.BeginInvoke((Action)delegate { Finish(lens.SampleAt(x, y)); });
                    return new IntPtr(1);
                }
                if (msg == Native.WM_RBUTTONDOWN)
                {
                    swallowUp = true;
                    lens.BeginInvoke((Action)delegate { Finish(null); });
                    return new IntPtr(1);
                }
                if (msg == Native.WM_MOUSEWHEEL)
                {
                    int delta = (short)((info.mouseData >> 16) & 0xFFFF);
                    lens.BeginInvoke((Action)delegate { ChangeZoom(delta); });
                    return new IntPtr(1); // la rotellina non deve far scorrere la finestra sotto
                }
            }
            if (nCode >= 0 && swallowUp)
            {
                int msg = wParam.ToInt32();
                if (msg == Native.WM_LBUTTONUP || msg == Native.WM_RBUTTONUP)
                {
                    swallowUp = false;
                    if (finished) lens.BeginInvoke((Action)ReleaseHook);
                    return new IntPtr(1);
                }
            }
            return Native.CallNextHookEx(mouseHook, nCode, wParam, lParam);
        }

        private void Collect(Color? c)
        {
            if (finished || !c.HasValue) return;
            collected++;
            lens.Collected = collected;
            try { onCollected(c.Value); } catch (Exception ex) { Log.Write("Prelievo multiplo: " + ex); }
        }

        private void UpdateLens()
        {
            if (finished) return;
            Native.POINT p;
            if (!Native.GetCursorPos(out p)) return;
            lens.Grab(p.X, p.Y);
            lens.MoveNear(p.X, p.Y);
        }

        private void Finish(Color? picked)
        {
            if (finished) return;
            finished = true;
            timer.Stop();
            UnregisterKeys();
            lens.Hide();
            Active = null;
            try
            {
                if (picked.HasValue && onPicked != null) onPicked(picked.Value);
            }
            catch (Exception ex) { Log.Write("Applicazione colore: " + ex); }
            finally
            {
                if (onEnd != null) onEnd();
            }
            // Se il tasto e' ancora premuto, l'aggancio resta finche' non arriva il rilascio
            // (cosi' Revit non riceve un "rilascio" orfano); comunque al massimo 1,5 secondi.
            if (!swallowUp) ReleaseHook();
            else
            {
                Timer safety = new Timer();
                safety.Interval = 1500;
                safety.Tick += delegate { safety.Dispose(); ReleaseHook(); };
                safety.Start();
            }
        }

        private void ReleaseHook()
        {
            if (mouseHook != IntPtr.Zero) { Native.UnhookWindowsHookEx(mouseHook); mouseHook = IntPtr.Zero; }
            Dispose();
        }

        public void Dispose()
        {
            if (mouseHook != IntPtr.Zero) { Native.UnhookWindowsHookEx(mouseHook); mouseHook = IntPtr.Zero; }
            timer.Dispose();
            if (!lens.IsDisposed) lens.Dispose();
        }
    }

    /// <summary>Lente d'ingrandimento che segue il cursore.</summary>
    internal sealed class MagnifierForm : Form
    {
        public event Action<int> HotkeyPressed;

        private const int LensBase = 135;   // lato della lente a 100%, in pixel
        private int zoom;
        private int area;
        private int radius;
        private Bitmap shot;
        private Color center = Color.Black;
        private float scale = 1f;
        private int collected;

        public MagnifierForm(int zoom, int area)
        {
            this.zoom = zoom;
            this.area = area;
            FormBorderStyle = FormBorderStyle.None;
            ShowInTaskbar = false;
            TopMost = true;
            StartPosition = FormStartPosition.Manual;
            DoubleBuffered = true;
            BackColor = Color.White;
            ApplyScale(1f);
        }

        public int Zoom
        {
            get { return zoom; }
            set { zoom = value; ApplyScale(scale); }
        }

        public int Area
        {
            get { return area; }
            set { area = value; Invalidate(); }
        }

        public int Collected
        {
            get { return collected; }
            set { collected = value; Invalidate(); }
        }

        protected override bool ShowWithoutActivation { get { return true; } }

        protected override CreateParams CreateParams
        {
            get
            {
                CreateParams cp = base.CreateParams;
                cp.ExStyle |= Native.WS_EX_TOOLWINDOW | Native.WS_EX_NOACTIVATE | Native.WS_EX_TOPMOST;
                return cp;
            }
        }

        public void ShowNoActivate()
        {
            if (!Visible) Show();
        }

        private int LensPx { get { return (int)Math.Round(LensBase * scale); } }

        private void ApplyScale(float s)
        {
            scale = s;
            // pixel visibili: dispari, con il pixel centrale al centro
            int n = (int)Math.Ceiling(LensPx / (double)zoom);
            if (n % 2 == 0) n++;
            if (n < 7) n = 7;
            radius = n / 2;
            if (shot != null) shot.Dispose();
            shot = new Bitmap(n, n);
            Size = new Size(LensPx + 2, LensPx + (int)Math.Round(56 * s));
            Invalidate();
        }

        public void Grab(int x, int y)
        {
            try
            {
                using (Graphics g = Graphics.FromImage(shot))
                    g.CopyFromScreen(x - radius, y - radius, 0, 0, shot.Size, CopyPixelOperation.SourceCopy);
                center = Average(shot, radius, radius, area);
            }
            catch (Exception) { /* es. schermo bloccato: si ignora */ }
            Invalidate();
        }

        /// <summary>Colore (media sull'area scelta) nel punto dello schermo indicato.</summary>
        public Color? SampleAt(int x, int y)
        {
            try
            {
                int r = area / 2;
                using (Bitmap bmp = new Bitmap(area, area))
                {
                    using (Graphics g = Graphics.FromImage(bmp))
                        g.CopyFromScreen(x - r, y - r, 0, 0, bmp.Size, CopyPixelOperation.SourceCopy);
                    return Average(bmp, r, r, area);
                }
            }
            catch (Exception ex)
            {
                Log.Write("Lettura pixel: " + ex.Message);
                return null;
            }
        }

        private static Color Average(Bitmap bmp, int cx, int cy, int size)
        {
            int r = size / 2;
            long sr = 0, sg = 0, sb = 0;
            int n = 0;
            for (int y = cy - r; y <= cy + r; y++)
                for (int x = cx - r; x <= cx + r; x++)
                {
                    if (x < 0 || y < 0 || x >= bmp.Width || y >= bmp.Height) continue;
                    Color c = bmp.GetPixel(x, y);
                    sr += c.R; sg += c.G; sb += c.B; n++;
                }
            if (n == 0) return Color.Black;
            return Color.FromArgb((int)Math.Round(sr / (double)n), (int)Math.Round(sg / (double)n), (int)Math.Round(sb / (double)n));
        }

        public void MoveNear(int x, int y)
        {
            float s = Native.ScaleForPoint(x, y);
            if (Math.Abs(s - scale) > 0.01f) ApplyScale(s);
            Rectangle wa = Native.WorkAreaForPoint(x, y);
            int off = (int)Math.Round(24 * s);
            int nx = x + off, ny = y + off;
            if (nx + Width > wa.Right) nx = x - off - Width;
            if (ny + Height > wa.Bottom) ny = y - off - Height;
            if (nx < wa.Left) nx = wa.Left;
            if (ny < wa.Top) ny = wa.Top;
            if (Left != nx || Top != ny) Location = new Point(nx, ny);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            Graphics g = e.Graphics;
            int lensPx = LensPx;
            int n = radius * 2 + 1;
            float cell = lensPx / (float)n;
            g.InterpolationMode = InterpolationMode.NearestNeighbor;
            g.PixelOffsetMode = PixelOffsetMode.Half;
            g.DrawImage(shot, new Rectangle(1, 1, lensPx, lensPx));
            g.PixelOffsetMode = PixelOffsetMode.Default;

            // riquadro sull'area campionata (1, 3 o 5 pixel)
            int r = area / 2;
            float x0 = 1 + (radius - r) * cell;
            float side = area * cell;
            using (Pen pw = new Pen(Color.White, 1f))
            using (Pen pb = new Pen(Color.Black, 1f))
            {
                g.DrawRectangle(pb, x0 - 1, x0 - 1, side + 1, side + 1);
                g.DrawRectangle(pw, x0, x0, side - 1, side - 1);
                g.DrawRectangle(pb, 0, 0, Width - 1, Height - 1);
            }

            // campione + valori
            int top = lensPx + 2;
            int infoH = (int)Math.Round(16 * scale);
            Rectangle sw = new Rectangle(1, top, Width - 2, Height - top - infoH - 1);
            using (SolidBrush b = new SolidBrush(center)) g.FillRectangle(b, sw);
            StringFormat sf = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center };
            using (Font f = new Font("Segoe UI", 11f * scale, FontStyle.Bold, GraphicsUnit.Pixel))
            using (SolidBrush tb = new SolidBrush(ColorText.Contrast(center)))
                g.DrawString(ColorText.ToHex(center) + "\nRGB " + ColorText.ToRgb(center), f, tb, sw, sf);

            Rectangle info = new Rectangle(1, Height - infoH - 1, Width - 2, infoH);
            using (SolidBrush ib = new SolidBrush(Color.FromArgb(40, 40, 40))) g.FillRectangle(ib, info);
            string t = "Area " + area + "×" + area + "  ·  Zoom " + zoom + "×" +
                       (collected > 0 ? "  ·  Presi " + collected : "");
            using (Font f2 = new Font("Segoe UI", 9.5f * scale, GraphicsUnit.Pixel))
                g.DrawString(t, f2, Brushes.White, info, sf);
        }

        protected override void WndProc(ref Message m)
        {
            if (m.Msg == Native.WM_HOTKEY && HotkeyPressed != null) HotkeyPressed(m.WParam.ToInt32());
            base.WndProc(ref m);
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing && shot != null) shot.Dispose();
            base.Dispose(disposing);
        }
    }
}
