using System;
using System.Drawing;
using System.Windows.Forms;

namespace CDVColori
{
    /// <summary>
    /// Riga di varianti: al centro il colore base, a sinistra le varianti piu' scure, a destra le piu' chiare.
    /// </summary>
    internal sealed class VariantStrip : Control
    {
        public const int PerLato = 4;

        /// <summary>Clic su una variante: colore e true se doppio clic (= applica e OK).</summary>
        public event Action<Color, bool> VariantClicked;
        /// <summary>Tasto destro su una variante.</summary>
        public event Action<Color, Point> VariantRightClicked;

        private Color? baseColor;
        private Color[] colors = new Color[0];
        private int hot = -1;
        private int selected = -1;
        private readonly ToolTip tip = new ToolTip();

        public VariantStrip()
        {
            SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer |
                     ControlStyles.UserPaint | ControlStyles.ResizeRedraw |
                     ControlStyles.StandardClick | ControlStyles.StandardDoubleClick, true);
            Cursor = Cursors.Hand;
        }

        public Color? BaseColor { get { return baseColor; } }

        /// <summary>Nuovo colore base: ricalcola le varianti.</summary>
        public void SetBase(Color c)
        {
            if (baseColor.HasValue && baseColor.Value.ToArgb() == c.ToArgb()) return;
            baseColor = Color.FromArgb(c.R, c.G, c.B);
            colors = ColorText.Variants(baseColor.Value, PerLato);
            selected = PerLato;
            Invalidate();
        }

        /// <summary>Segna come selezionata la variante uguale al colore dato (se c'e').</summary>
        public void MarkSelected(Color c)
        {
            int idx = Array.FindIndex(colors, x => x.R == c.R && x.G == c.G && x.B == c.B);
            if (idx != selected) { selected = idx; Invalidate(); }
        }

        public bool Contains(Color c)
        {
            return Array.Exists(colors, x => x.R == c.R && x.G == c.G && x.B == c.B);
        }

        private Rectangle Cell(int i)
        {
            int n = colors.Length;
            if (n == 0) return Rectangle.Empty;
            float w = Width / (float)n;
            int x0 = (int)Math.Round(i * w);
            int x1 = (int)Math.Round((i + 1) * w);
            return new Rectangle(x0, 0, x1 - x0, Height);
        }

        private int HitTest(Point p)
        {
            if (colors.Length == 0 || p.Y < 0 || p.Y >= Height) return -1;
            int i = (int)(p.X / (Width / (float)colors.Length));
            return i >= 0 && i < colors.Length ? i : -1;
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            Graphics g = e.Graphics;
            g.Clear(Parent != null ? Parent.BackColor : SystemColors.Control);
            if (colors.Length == 0)
            {
                using (SolidBrush b = new SolidBrush(SystemColors.GrayText))
                    g.DrawString("(nessun colore)", Font, b, 2, 2);
                return;
            }
            for (int i = 0; i < colors.Length; i++)
            {
                Rectangle r = Cell(i);
                using (SolidBrush b = new SolidBrush(colors[i])) g.FillRectangle(b, r);
            }
            using (Pen thin = new Pen(Color.FromArgb(140, 140, 140)))
                g.DrawRectangle(thin, 0, 0, Width - 1, Height - 1);

            // colore base: piccolo segno sotto
            Rectangle rb = Cell(PerLato);
            using (SolidBrush mark = new SolidBrush(ColorText.Contrast(colors[PerLato])))
            {
                int d = Math.Max(4, Height / 5);
                Point c = new Point(rb.Left + rb.Width / 2, rb.Bottom - d - 2);
                g.FillPolygon(mark, new[] { new Point(c.X - d, c.Y + d), new Point(c.X + d, c.Y + d), new Point(c.X, c.Y) });
            }
            if (selected >= 0) DrawFrame(g, Cell(selected), Color.Black, Color.White);
            if (hot >= 0 && hot != selected) DrawFrame(g, Cell(hot), Color.FromArgb(0, 120, 215), Color.White);
        }

        private static void DrawFrame(Graphics g, Rectangle r, Color outer, Color inner)
        {
            using (Pen po = new Pen(outer, 2f)) g.DrawRectangle(po, r.Left + 1, r.Top + 1, r.Width - 2, r.Height - 2);
            using (Pen pi = new Pen(inner, 1f)) g.DrawRectangle(pi, r.Left + 2, r.Top + 2, r.Width - 5, r.Height - 5);
        }

        protected override void OnMouseMove(MouseEventArgs e)
        {
            int i = HitTest(e.Location);
            if (i != hot)
            {
                hot = i;
                Invalidate();
                tip.SetToolTip(this, i >= 0 ? Describe(i) : "");
            }
            base.OnMouseMove(e);
        }

        protected override void OnMouseLeave(EventArgs e)
        {
            hot = -1;
            Invalidate();
            base.OnMouseLeave(e);
        }

        private string Describe(int i)
        {
            string what = i == PerLato ? "Colore attuale"
                        : i < PerLato ? "Più scuro " + (PerLato - i)
                        : "Più chiaro " + (i - PerLato);
            return what + "\nRGB " + ColorText.ToRgb(colors[i]) + "   " + ColorText.ToHex(colors[i]);
        }

        protected override void OnMouseClick(MouseEventArgs e)
        {
            base.OnMouseClick(e);
            int i = HitTest(e.Location);
            if (i < 0) return;
            if (e.Button == MouseButtons.Left)
            {
                selected = i;
                Invalidate();
                if (VariantClicked != null) VariantClicked(colors[i], false);
            }
            else if (e.Button == MouseButtons.Right && VariantRightClicked != null)
            {
                VariantRightClicked(colors[i], e.Location);
            }
        }

        protected override void OnMouseDoubleClick(MouseEventArgs e)
        {
            base.OnMouseDoubleClick(e);
            int i = HitTest(e.Location);
            if (i >= 0 && e.Button == MouseButtons.Left && VariantClicked != null) VariantClicked(colors[i], true);
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing) tip.Dispose();
            base.Dispose(disposing);
        }
    }
}
