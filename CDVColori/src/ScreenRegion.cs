using System;
using System.Drawing;
using System.Windows.Forms;

namespace CDVColori
{
    /// <summary>
    /// Cattura di una zona dello schermo: lo schermo viene "congelato" e si trascina un rettangolo.
    /// Esc o clic destro annullano.
    /// </summary>
    internal sealed class ScreenRegion : Form
    {
        private readonly Bitmap screen;
        private readonly Rectangle virt;
        private Point start;
        private Rectangle sel = Rectangle.Empty;
        private bool dragging;

        private Rectangle Selection { get { return sel; } }

        private ScreenRegion(Bitmap screen, Rectangle virt)
        {
            this.screen = screen;
            this.virt = virt;
            FormBorderStyle = FormBorderStyle.None;
            ShowInTaskbar = false;
            TopMost = true;
            StartPosition = FormStartPosition.Manual;
            Bounds = virt;
            DoubleBuffered = true;
            Cursor = Cursors.Cross;
            KeyPreview = true;
        }

        /// <summary>Restituisce l'immagine della zona scelta, o null se annullato.</summary>
        public static Bitmap CaptureRegion()
        {
            Rectangle virt = SystemInformation.VirtualScreen;
            Bitmap shot = new Bitmap(virt.Width, virt.Height);
            using (Graphics g = Graphics.FromImage(shot))
                g.CopyFromScreen(virt.Left, virt.Top, 0, 0, virt.Size, CopyPixelOperation.SourceCopy);
            using (ScreenRegion f = new ScreenRegion(shot, virt))
            {
                Bitmap res = null;
                Rectangle r = f.Selection;
                if (f.ShowDialog() == DialogResult.OK && (r = f.Selection).Width > 3 && r.Height > 3)
                    res = shot.Clone(r, shot.PixelFormat);
                shot.Dispose();
                return res;
            }
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            Graphics g = e.Graphics;
            g.DrawImageUnscaled(screen, 0, 0);
            using (SolidBrush dim = new SolidBrush(Color.FromArgb(110, 0, 0, 0)))
            {
                if (sel.IsEmpty) g.FillRectangle(dim, ClientRectangle);
                else
                {
                    using (Region r = new Region(ClientRectangle))
                    {
                        r.Exclude(sel);
                        g.FillRegion(dim, r);
                    }
                    using (Pen p = new Pen(Color.FromArgb(0, 140, 255), 2f)) g.DrawRectangle(p, sel);
                }
            }
            string hint = "Trascina per scegliere la zona da cui estrarre i colori  ·  Esc per annullare";
            using (Font f = new Font("Segoe UI", 15f, GraphicsUnit.Pixel))
            {
                SizeF sz = g.MeasureString(hint, f);
                Screen scr = Screen.FromPoint(Cursor.Position);
                Rectangle sb = RectangleToClient(scr.Bounds);
                RectangleF box = new RectangleF(sb.Left + (sb.Width - sz.Width) / 2 - 10, sb.Top + 20, sz.Width + 20, sz.Height + 10);
                using (SolidBrush bg = new SolidBrush(Color.FromArgb(200, 30, 30, 30))) g.FillRectangle(bg, box);
                g.DrawString(hint, f, Brushes.White, box.Left + 10, box.Top + 5);
            }
        }

        protected override void OnMouseDown(MouseEventArgs e)
        {
            if (e.Button == MouseButtons.Right) { DialogResult = DialogResult.Cancel; return; }
            if (e.Button != MouseButtons.Left) return;
            dragging = true;
            start = e.Location;
            sel = new Rectangle(e.Location, Size.Empty);
            Invalidate();
        }

        protected override void OnMouseMove(MouseEventArgs e)
        {
            if (!dragging) return;
            sel = Rectangle.FromLTRB(Math.Min(start.X, e.X), Math.Min(start.Y, e.Y), Math.Max(start.X, e.X), Math.Max(start.Y, e.Y));
            Invalidate();
        }

        protected override void OnMouseUp(MouseEventArgs e)
        {
            if (!dragging || e.Button != MouseButtons.Left) return;
            dragging = false;
            DialogResult = sel.Width > 3 && sel.Height > 3 ? DialogResult.OK : DialogResult.Cancel;
        }

        protected override void OnKeyDown(KeyEventArgs e)
        {
            if (e.KeyCode == Keys.Escape) DialogResult = DialogResult.Cancel;
            base.OnKeyDown(e);
        }
    }
}
