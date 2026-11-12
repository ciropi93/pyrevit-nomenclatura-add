using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace CDVColori
{
    /// <summary>
    /// Contagocce: mostra una lente vicino al cursore e al clic sinistro legge il colore del pixel sotto il cursore,
    /// ovunque sullo schermo (anche fuori da Revit). Clic destro o Esc annullano.
    /// L'aggancio al mouse resta attivo solo durante la scelta.
    /// </summary>
    public sealed class PickSession : IDisposable
    {
        private const int HotkeyId = 0xCD01;
        private const int Radius = 7;          // area letta: 15x15 pixel
        private const int Zoom = 9;            // ingrandimento della lente

        private readonly Action<Color> onPicked;
        private readonly Action onEnd;
        private readonly Native.LowLevelMouseProc mouseProc;
        private IntPtr mouseHook = IntPtr.Zero;
        private readonly MagnifierForm lens;
        private readonly Timer timer;
        private bool swallowUp;
        private bool finished;

        public static PickSession Active { get; private set; }

        private PickSession(Action<Color> onPicked, Action onEnd)
        {
            this.onPicked = onPicked;
            this.onEnd = onEnd;
            mouseProc = MouseHookProc;
            lens = new MagnifierForm(Radius, Zoom);
            lens.HotkeyPressed += delegate { Finish(null); };
            timer = new Timer();
            timer.Interval = 30;
            timer.Tick += delegate { UpdateLens(); };
        }

        /// <summary>Avvia la scelta del colore. onPicked riceve il colore; onEnd viene chiamato sempre alla fine.</summary>
        public static void Start(Action<Color> onPicked, Action onEnd)
        {
            if (Active != null) return;
            PickSession s = new PickSession(onPicked, onEnd);
            Active = s;
            s.Begin();
        }

        private void Begin()
        {
            UpdateLens();
            lens.ShowNoActivate();
            Native.RegisterHotKey(lens.Handle, HotkeyId, 0, Native.VK_ESCAPE);
            mouseHook = Native.SetWindowsHookEx(Native.WH_MOUSE_LL, mouseProc, Native.GetModuleHandle(null), 0);
            if (mouseHook == IntPtr.Zero)
            {
                Log.Write("Aggancio mouse non riuscito: " + Marshal.GetLastWin32Error());
                Finish(null);
                return;
            }
            timer.Start();
        }

        private IntPtr MouseHookProc(int nCode, IntPtr wParam, IntPtr lParam)
        {
            if (nCode >= 0 && !finished)
            {
                int msg = wParam.ToInt32();
                if (msg == Native.WM_LBUTTONDOWN)
                {
                    Native.MSLLHOOKSTRUCT info = (Native.MSLLHOOKSTRUCT)Marshal.PtrToStructure(lParam, typeof(Native.MSLLHOOKSTRUCT));
                    int x = info.pt.X, y = info.pt.Y;
                    swallowUp = true;
                    // il lavoro vero va fuori dall'aggancio, che deve rispondere subito
                    lens.BeginInvoke((Action)delegate { Finish(ReadPixel(x, y)); });
                    return new IntPtr(1);
                }
                if (msg == Native.WM_RBUTTONDOWN)
                {
                    swallowUp = true;
                    lens.BeginInvoke((Action)delegate { Finish(null); });
                    return new IntPtr(1);
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

        private static Color? ReadPixel(int x, int y)
        {
            try
            {
                using (Bitmap bmp = new Bitmap(1, 1))
                {
                    using (Graphics g = Graphics.FromImage(bmp))
                        g.CopyFromScreen(x, y, 0, 0, new Size(1, 1), CopyPixelOperation.SourceCopy);
                    Color c = bmp.GetPixel(0, 0);
                    return Color.FromArgb(c.R, c.G, c.B);
                }
            }
            catch (Exception ex)
            {
                Log.Write("Lettura pixel: " + ex.Message);
                return null;
            }
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
            Native.UnregisterHotKey(lens.Handle, HotkeyId);
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
        public event Action HotkeyPressed;

        private readonly int radius, zoom;
        private readonly Bitmap shot;
        private Color center = Color.Black;
        private float scale = 1f;

        public MagnifierForm(int radius, int zoom)
        {
            this.radius = radius;
            this.zoom = zoom;
            int n = radius * 2 + 1;
            shot = new Bitmap(n, n);
            FormBorderStyle = FormBorderStyle.None;
            ShowInTaskbar = false;
            TopMost = true;
            StartPosition = FormStartPosition.Manual;
            DoubleBuffered = true;
            BackColor = Color.White;
            ApplyScale(1f);
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

        private void ApplyScale(float s)
        {
            scale = s;
            int lensPx = (int)Math.Round((radius * 2 + 1) * zoom * s);
            Size = new Size(lensPx + 2, lensPx + (int)Math.Round(40 * s));
        }

        public void Grab(int x, int y)
        {
            try
            {
                using (Graphics g = Graphics.FromImage(shot))
                    g.CopyFromScreen(x - radius, y - radius, 0, 0, shot.Size, CopyPixelOperation.SourceCopy);
                center = shot.GetPixel(radius, radius);
            }
            catch (Exception) { /* es. schermo bloccato: si ignora */ }
            Invalidate();
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
            int lensPx = Width - 2;
            g.InterpolationMode = InterpolationMode.NearestNeighbor;
            g.PixelOffsetMode = PixelOffsetMode.Half;
            g.DrawImage(shot, new Rectangle(1, 1, lensPx, lensPx));
            g.PixelOffsetMode = PixelOffsetMode.Default;

            // riquadro sul pixel centrale
            float cell = lensPx / (float)(radius * 2 + 1);
            float cx = 1 + radius * cell;
            using (Pen pw = new Pen(Color.White, 1f))
            using (Pen pb = new Pen(Color.Black, 1f))
            {
                g.DrawRectangle(pb, cx - 1, cx - 1, cell + 1, cell + 1);
                g.DrawRectangle(pw, cx, cx, cell - 1, cell - 1);
                g.DrawRectangle(pb, 0, 0, Width - 1, Height - 1);
            }

            // campione + valori
            int top = lensPx + 2;
            int h = Height - top - 1;
            Rectangle sw = new Rectangle(1, top, Width - 2, h);
            using (SolidBrush b = new SolidBrush(center)) g.FillRectangle(b, sw);
            using (Font f = new Font("Segoe UI", 11f * scale, FontStyle.Bold, GraphicsUnit.Pixel))
            using (SolidBrush tb = new SolidBrush(ColorText.Contrast(center)))
            {
                string t = ColorText.ToHex(center) + "\nRGB " + ColorText.ToRgb(center);
                StringFormat sf = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center };
                g.DrawString(t, f, tb, sw, sf);
            }
        }

        protected override void WndProc(ref Message m)
        {
            if (m.Msg == Native.WM_HOTKEY && HotkeyPressed != null) HotkeyPressed();
            base.WndProc(ref m);
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing) shot.Dispose();
            base.Dispose(disposing);
        }
    }
}
