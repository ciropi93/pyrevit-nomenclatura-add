using System;
using System.Drawing;
using System.Windows.Forms;

namespace CDVColori
{
    /// <summary>
    /// Riga di varianti del colore base (luminosita', saturazione, tinta o armonie: vedi ColorText.Variants).
    /// Il colore base e' segnato da un triangolino; nelle armonie i gruppi sono separati da uno spazio.
    /// </summary>
    internal sealed class VariantStrip : Control
    {
        /// <summary>Clic su una variante: colore e true se doppio clic (= applica e OK).</summary>
        public event Action<Color, bool> VariantClicked;
        /// <summary>Tasto destro su una variante.</summary>
        public event Action<Color, Point> VariantRightClicked;

        private Color? baseColor;
        private VariantMode mode = VariantMode.Luminosita;
        private int passi = 4;
        private VariantSet set;
        private Rectangle[] cells = new Rectangle[0];
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

        /// <summary>Cambia modalita' e numero di passi, mantenendo il colore base.</summary>
        public void SetMode(VariantMode m, int p)
        {
            mode = m;
            passi = p;
            Recompute();
        }

        /// <summary>Nuovo colore base: ricalcola le varianti.</summary>
        public void SetBase(Color c)
        {
            if (baseColor.HasValue && ColorText.SameRgb(baseColor.Value, c)) return;
            baseColor = Color.FromArgb(c.R, c.G, c.B);
            Recompute();
        }

        private void Recompute()
        {
            if (!baseColor.HasValue) { set = null; cells = new Rectangle[0]; Invalidate(); return; }
            set = ColorText.Variants(baseColor.Value, mode, passi);
            selected = set.BaseIndex;
            hot = -1;
            Layout_();
            Invalidate();
        }

        /// <summary>Segna come selezionata la variante uguale al colore dato (se c'e').</summary>
        public void MarkSelected(Color c)
        {
            int idx = set == null ? -1 : Array.FindIndex(set.Colors, x => ColorText.SameRgb(x, c));
            if (idx != selected) { selected = idx; Invalidate(); }
        }

        public bool Contains(Color c)
        {
            return set != null && Array.Exists(set.Colors, x => ColorText.SameRgb(x, c));
        }

        protected override void OnResize(EventArgs e)
        {
            base.OnResize(e);
            Layout_();
        }

        /// <summary>Calcola i riquadri: larghezza uguale, piu' uno spazio prima di ogni gruppo.</summary>
        private void Layout_()
        {
            if (set == null) { cells = new Rectangle[0]; return; }
            int n = set.Colors.Length;
            int gaps = set.GroupStarts.Length;
            int gap = gaps > 0 ? Math.Max(4, Height / 5) : 0;
            float w = (Width - gaps * gap) / (float)n;
            cells = new Rectangle[n];
            float x = 0;
            for (int i = 0; i < n; i++)
            {
                if (Array.IndexOf(set.GroupStarts, i) >= 0) x += gap;
                int x0 = (int)Math.Round(x);
                int x1 = (int)Math.Round(x + w);
                cells[i] = new Rectangle(x0, 0, Math.Max(1, x1 - x0), Height);
                x += w;
            }
        }

        private int HitTest(Point p)
        {
            for (int i = 0; i < cells.Length; i++) if (cells[i].Contains(p)) return i;
            return -1;
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            Graphics g = e.Graphics;
            g.Clear(Parent != null ? Parent.BackColor : SystemColors.Control);
            if (set == null || cells.Length == 0)
            {
                using (SolidBrush b = new SolidBrush(SystemColors.GrayText))
                    g.DrawString("(nessun colore)", Font, b, 2, 2);
                return;
            }
            using (Pen thin = new Pen(Color.FromArgb(140, 140, 140)))
            {
                for (int i = 0; i < cells.Length; i++)
                {
                    using (SolidBrush b = new SolidBrush(set.Colors[i])) g.FillRectangle(b, cells[i]);
                    bool groupStart = i == 0 || Array.IndexOf(set.GroupStarts, i) >= 0;
                    bool groupEnd = i == cells.Length - 1 || Array.IndexOf(set.GroupStarts, i + 1) >= 0;
                    Rectangle r = cells[i];
                    g.DrawLine(thin, r.Left, 0, r.Right - 1, 0);
                    g.DrawLine(thin, r.Left, Height - 1, r.Right - 1, Height - 1);
                    if (groupStart) g.DrawLine(thin, r.Left, 0, r.Left, Height - 1);
                    if (groupEnd) g.DrawLine(thin, r.Right - 1, 0, r.Right - 1, Height - 1);
                }
            }

            // colore base: triangolino in basso
            Rectangle rb = cells[set.BaseIndex];
            using (SolidBrush mark = new SolidBrush(ColorText.Contrast(set.Colors[set.BaseIndex])))
            {
                int d = Math.Max(3, Math.Min(Height / 5, rb.Width / 3));
                Point c = new Point(rb.Left + rb.Width / 2, rb.Bottom - d - 2);
                g.FillPolygon(mark, new[] { new Point(c.X - d, c.Y + d), new Point(c.X + d, c.Y + d), new Point(c.X, c.Y) });
            }
            if (selected >= 0 && selected < cells.Length) DrawFrame(g, cells[selected], Color.Black, Color.White);
            if (hot >= 0 && hot != selected && hot < cells.Length) DrawFrame(g, cells[hot], Color.FromArgb(0, 120, 215), Color.White);
        }

        private static void DrawFrame(Graphics g, Rectangle r, Color outer, Color inner)
        {
            if (r.Width < 6) return;
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
                tip.SetToolTip(this, i >= 0 ? set.Labels[i] + "\nRGB " + ColorText.ToRgb(set.Colors[i]) +
                    "   " + ColorText.ToHex(set.Colors[i]) : "");
            }
            base.OnMouseMove(e);
        }

        protected override void OnMouseLeave(EventArgs e)
        {
            hot = -1;
            Invalidate();
            base.OnMouseLeave(e);
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
                if (VariantClicked != null) VariantClicked(set.Colors[i], false);
            }
            else if (e.Button == MouseButtons.Right && VariantRightClicked != null)
            {
                VariantRightClicked(set.Colors[i], e.Location);
            }
        }

        protected override void OnMouseDoubleClick(MouseEventArgs e)
        {
            base.OnMouseDoubleClick(e);
            int i = HitTest(e.Location);
            if (i >= 0 && e.Button == MouseButtons.Left && VariantClicked != null) VariantClicked(set.Colors[i], true);
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing) tip.Dispose();
            base.Dispose(disposing);
        }
    }
}
