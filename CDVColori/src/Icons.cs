using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Runtime.InteropServices;

namespace CDVColori
{
    /// <summary>Icone disegnate a codice (nessun file esterno).</summary>
    internal static class Icons
    {
        /// <summary>Contagocce con la punta in basso a sinistra, dentro il rettangolo dato.</summary>
        public static void DrawEyedropper(Graphics g, RectangleF r, Color body, Color tip)
        {
            GraphicsState st = g.Save();
            g.SmoothingMode = SmoothingMode.AntiAlias;
            float s = Math.Min(r.Width, r.Height) / 16f;
            g.TranslateTransform(r.X + r.Width / 2f, r.Y + r.Height / 2f);
            g.ScaleTransform(s, s);
            g.RotateTransform(45f);
            // coordinate in un riquadro 16x16 centrato sull'origine, punta verso il basso
            using (SolidBrush bBody = new SolidBrush(body))
            using (SolidBrush bTip = new SolidBrush(tip))
            using (Pen pTip = new Pen(body, 0.6f))
            {
                // bulbo
                g.FillEllipse(bBody, -2.3f, -8.2f, 4.6f, 4.4f);
                // collare
                g.FillRectangle(bBody, -3.2f, -4.4f, 6.4f, 1.4f);
                // corpo
                g.FillRectangle(bBody, -1.7f, -3.2f, 3.4f, 5.2f);
                // cannuccia trasparente con il colore
                using (GraphicsPath path = new GraphicsPath())
                {
                    path.AddPolygon(new[]
                    {
                        new PointF(-1.2f, 2.0f), new PointF(1.2f, 2.0f),
                        new PointF(0.5f, 7.0f), new PointF(0f, 8.2f), new PointF(-0.5f, 7.0f)
                    });
                    g.FillPath(bTip, path);
                    g.DrawPath(pTip, path);
                }
            }
            g.Restore(st);
        }

        [DllImport("user32.dll")]
        private static extern bool DestroyIcon(IntPtr hIcon);

        /// <summary>Icona dell'area di notifica: contagocce con goccia colorata.</summary>
        public static Icon TrayIcon(int size, bool active)
        {
            using (Bitmap bmp = new Bitmap(size, size))
            {
                using (Graphics g = Graphics.FromImage(bmp))
                {
                    g.Clear(Color.Transparent);
                    g.SmoothingMode = SmoothingMode.AntiAlias;
                    Color body = active ? Color.FromArgb(40, 40, 40) : Color.FromArgb(150, 150, 150);
                    Color tip = active ? Color.FromArgb(0, 140, 255) : Color.FromArgb(200, 200, 200);
                    // nell'area di notifica lo sfondo puo' essere scuro: alone chiaro attorno
                    using (SolidBrush halo = new SolidBrush(Color.FromArgb(220, 255, 255, 255)))
                        g.FillEllipse(halo, 0, 0, size - 1, size - 1);
                    DrawEyedropper(g, new RectangleF(size * 0.08f, size * 0.08f, size * 0.84f, size * 0.84f), body, tip);
                }
                IntPtr h = bmp.GetHicon();
                Icon ico = (Icon)Icon.FromHandle(h).Clone();
                DestroyIcon(h);
                return ico;
            }
        }
    }
}
