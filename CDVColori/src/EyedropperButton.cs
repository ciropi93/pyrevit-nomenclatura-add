using System;
using System.Drawing;
using System.Windows.Forms;

namespace CDVColori
{
    /// <summary>
    /// Pulsante contagocce appoggiato sulla finestra Colore, a sinistra di "Aggiungi".
    /// E' una finestra nostra "di proprieta'" della finestra Colore: la segue e le resta sopra.
    /// Non prende il fuoco, quindi la finestra Colore resta attiva.
    /// </summary>
    internal sealed class EyedropperButton : Form
    {
        public event Action Clicked;

        private bool hot, pressed, picking;
        private readonly ToolTip tip = new ToolTip();

        public EyedropperButton()
        {
            FormBorderStyle = FormBorderStyle.None;
            ShowInTaskbar = false;
            StartPosition = FormStartPosition.Manual;
            DoubleBuffered = true;
            BackColor = SystemColors.Control;
            Size = new Size(24, 24);
            tip.SetToolTip(this, "Contagocce: prendi un colore dallo schermo\n(clic destro o Esc per annullare)");
        }

        protected override bool ShowWithoutActivation { get { return true; } }

        protected override CreateParams CreateParams
        {
            get
            {
                CreateParams cp = base.CreateParams;
                cp.ExStyle |= Native.WS_EX_TOOLWINDOW | Native.WS_EX_NOACTIVATE;
                return cp;
            }
        }

        public bool Picking
        {
            get { return picking; }
            set { picking = value; Invalidate(); }
        }

        /// <summary>Posiziona il pulsante a sinistra del pulsante "Aggiungi" (o, in mancanza, sopra a OK).</summary>
        public void PlaceOn(ColorDialogTarget t)
        {
            Rectangle anchor = t.ControlRect(ColorDialogTarget.ID_ADD);
            float s = t.Scale;
            int gap = (int)Math.Round(8 * s);
            int size;
            int x, y;
            if (!anchor.IsEmpty)
            {
                size = anchor.Height;
                x = anchor.Left - gap - size;
                y = anchor.Top;
            }
            else
            {
                Rectangle ok = t.ControlRect(Native.IDOK);
                size = (int)Math.Round(24 * s);
                if (ok.IsEmpty)
                {
                    Rectangle b = t.Bounds;
                    x = b.Left + gap; y = b.Bottom - size - gap;
                }
                else
                {
                    x = ok.Left - gap - size; y = ok.Top;
                }
            }
            Bounds = new Rectangle(x, y, size, size);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            Graphics g = e.Graphics;
            Rectangle r = new Rectangle(0, 0, Width - 1, Height - 1);
            Color back = picking ? Color.FromArgb(204, 228, 247)
                       : pressed ? Color.FromArgb(204, 228, 247)
                       : hot ? Color.FromArgb(229, 241, 251)
                       : Color.FromArgb(225, 225, 225);
            Color border = (hot || picking) ? Color.FromArgb(0, 120, 215) : Color.FromArgb(173, 173, 173);
            using (SolidBrush b = new SolidBrush(back)) g.FillRectangle(b, r);
            using (Pen p = new Pen(border)) g.DrawRectangle(p, r);
            float pad = Width * 0.16f;
            Icons.DrawEyedropper(g, new RectangleF(pad, pad, Width - 2 * pad, Height - 2 * pad),
                Color.FromArgb(45, 45, 45), Color.FromArgb(0, 140, 255));
        }

        protected override void OnMouseEnter(EventArgs e) { hot = true; Invalidate(); base.OnMouseEnter(e); }
        protected override void OnMouseLeave(EventArgs e) { hot = false; pressed = false; Invalidate(); base.OnMouseLeave(e); }
        protected override void OnMouseDown(MouseEventArgs e)
        {
            if (e.Button == MouseButtons.Left) { pressed = true; Invalidate(); }
            base.OnMouseDown(e);
        }
        protected override void OnMouseUp(MouseEventArgs e)
        {
            bool fire = pressed && e.Button == MouseButtons.Left && ClientRectangle.Contains(e.Location);
            pressed = false;
            Invalidate();
            base.OnMouseUp(e);
            if (fire && Clicked != null) Clicked();
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing) tip.Dispose();
            base.Dispose(disposing);
        }
    }
}
