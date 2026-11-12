using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Windows.Forms;

namespace CDVColori
{
    /// <summary>
    /// Pannello delle palette, agganciato a destra (o a sinistra) della finestra Colore.
    /// Clic su un colore = lo scrive nella finestra Colore; doppio clic = scrive e preme OK.
    /// </summary>
    internal sealed class PalettePanel : Form
    {
        /// <summary>Applica il colore alla finestra Colore; il bool indica se premere anche OK.</summary>
        public Func<Color, bool, bool> ApplyColor;
        /// <summary>Legge il colore attuale della finestra Colore.</summary>
        public Func<Color?> ReadCurrent;

        private readonly Settings settings;
        private readonly float s;
        private List<Palette> palettes = new List<Palette>();

        private readonly ComboBox cmbPalette = new ComboBox();
        private readonly Button btnMenu = new Button();
        private readonly FlowLayoutPanel grid = new FlowLayoutPanel();
        private readonly Label lblHint = new Label();
        private readonly TextBox txtValue = new TextBox();
        private readonly Button btnApply = new Button();
        private readonly Button btnAdd = new Button();
        private readonly ToolTip tip = new ToolTip();
        private readonly ContextMenuStrip menuPalette = new ContextMenuStrip();

        public float ScaleFactor { get { return s; } }

        public PalettePanel(Settings settings, float scale)
        {
            this.settings = settings;
            s = scale;
            Text = "CDV Colori";
            FormBorderStyle = FormBorderStyle.FixedToolWindow;
            ControlBox = false;
            ShowInTaskbar = false;
            StartPosition = FormStartPosition.Manual;
            AutoScaleMode = AutoScaleMode.None;
            Font = new Font("Segoe UI", 12f * s, GraphicsUnit.Pixel);
            BackColor = SystemColors.Control;
            KeyPreview = true;

            cmbPalette.DropDownStyle = ComboBoxStyle.DropDownList;
            cmbPalette.SelectedIndexChanged += delegate { ShowSelected(); };

            btnMenu.Text = "…";
            btnMenu.Click += delegate { menuPalette.Show(btnMenu, new Point(0, btnMenu.Height)); };
            tip.SetToolTip(btnMenu, "Gestione palette");

            grid.AutoScroll = true;
            grid.WrapContents = true;
            grid.BackColor = SystemColors.Window;
            grid.BorderStyle = BorderStyle.FixedSingle;
            grid.Padding = new Padding(Px(3));

            lblHint.Text = "Clic: applica  ·  Doppio clic: applica e OK";
            lblHint.ForeColor = SystemColors.GrayText;
            lblHint.AutoSize = false;

            txtValue.Text = "";
            tip.SetToolTip(txtValue, "Scrivi #RRGGBB oppure R,G,B (es. 128,64,0) e premi Invio");
            txtValue.KeyDown += delegate (object o, KeyEventArgs e)
            {
                if (e.KeyCode == Keys.Enter) { e.SuppressKeyPress = true; ApplyTyped(); }
            };

            btnApply.Text = "Applica";
            btnApply.Click += delegate { ApplyTyped(); };

            btnAdd.Text = "+ Aggiungi colore attuale";
            btnAdd.Click += delegate { AddCurrent(); };
            tip.SetToolTip(btnAdd, "Salva nella palette il colore ora impostato nella finestra Colore");

            menuPalette.Items.Add("Nuova palette…", null, delegate { NewPalette(); });
            menuPalette.Items.Add("Rinomina palette…", null, delegate { RenamePalette(); });
            menuPalette.Items.Add("Elimina palette…", null, delegate { DeletePalette(); });
            menuPalette.Items.Add(new ToolStripSeparator());
            menuPalette.Items.Add("Svuota recenti", null, delegate { ClearRecent(); });
            menuPalette.Items.Add(new ToolStripSeparator());
            menuPalette.Items.Add("Apri cartella palette", null, delegate { OpenFolder(settings.PaletteDir); });
            menuPalette.Items.Add("Ricarica", null, delegate { Reload(); });

            Controls.AddRange(new Control[] { cmbPalette, btnMenu, grid, lblHint, txtValue, btnApply, btnAdd });
            ClientSize = new Size(Px(248), Px(400));
            Reload();
        }

        private int Px(float v) { return (int)Math.Round(v * s); }

        protected override CreateParams CreateParams
        {
            get
            {
                CreateParams cp = base.CreateParams;
                cp.ExStyle |= Native.WS_EX_TOOLWINDOW;
                return cp;
            }
        }

        protected override bool ShowWithoutActivation { get { return true; } }

        protected override void OnLayout(LayoutEventArgs e)
        {
            base.OnLayout(e);
            int m = Px(6), h = Px(26), w = ClientSize.Width;
            btnMenu.SetBounds(w - m - h, m, h, h);
            cmbPalette.SetBounds(m, m + Px(1), w - 3 * m - h + m, h);
            int bottom = ClientSize.Height - m;
            btnAdd.SetBounds(m, bottom - h, w - 2 * m, h);
            bottom -= h + Px(4);
            int bw = Px(64);
            btnApply.SetBounds(w - m - bw, bottom - h, bw, h);
            txtValue.SetBounds(m, bottom - h + Px(2), w - 3 * m - bw + m - Px(2), h);
            bottom -= h + Px(4);
            lblHint.SetBounds(m, bottom - Px(18), w - 2 * m, Px(18));
            bottom -= Px(20);
            int top = m + h + Px(6);
            grid.SetBounds(m, top, w - 2 * m, Math.Max(Px(40), bottom - top));
        }

        /// <summary>Rilegge le palette dal disco (all'apertura di ogni finestra Colore).</summary>
        public void Reload()
        {
            string keep = cmbPalette.SelectedItem != null ? ((Palette)cmbPalette.SelectedItem).Nome : settings.ultimaPalette;
            palettes = PaletteStore.LoadAll(settings.PaletteDir);
            cmbPalette.BeginUpdate();
            cmbPalette.Items.Clear();
            foreach (Palette p in palettes) cmbPalette.Items.Add(p);
            cmbPalette.EndUpdate();
            int idx = palettes.FindIndex(p => p.Nome == keep);
            if (idx < 0) idx = palettes.Count > 1 ? 1 : 0;
            cmbPalette.SelectedIndex = idx;
            ShowSelected();
        }

        private Palette Selected { get { return cmbPalette.SelectedItem as Palette; } }

        private Palette Recenti { get { return palettes.Count > 0 ? palettes[0] : null; } }

        private void ShowSelected()
        {
            Palette p = Selected;
            if (p == null) return;
            if (!p.IsRecent && settings.ultimaPalette != p.Nome)
            {
                settings.ultimaPalette = p.Nome;
                settings.Save();
            }
            btnAdd.Enabled = !p.IsRecent;
            grid.SuspendLayout();
            foreach (Control c in grid.Controls) c.Dispose();
            grid.Controls.Clear();
            foreach (VoceColore v in p.Colori) grid.Controls.Add(MakeSwatch(p, v));
            if (p.Colori.Count == 0)
            {
                Label empty = new Label();
                empty.AutoSize = true;
                empty.ForeColor = SystemColors.GrayText;
                empty.Text = p.IsRecent
                    ? "I colori che applichi da qui\ncompariranno in questo elenco."
                    : "Palette vuota: imposta un colore\nnella finestra e premi \"+ Aggiungi\".";
                grid.Controls.Add(empty);
            }
            grid.ResumeLayout();
        }

        private Swatch MakeSwatch(Palette p, VoceColore v)
        {
            Swatch sw = new Swatch(v);
            int size = Px(26);
            sw.Size = new Size(size, size);
            sw.Margin = new Padding(Px(2));
            tip.SetToolTip(sw, ColorText.Describe(v));
            sw.MouseClick += delegate (object o, MouseEventArgs e)
            {
                if (e.Button == MouseButtons.Left) Apply(v.ToColor(), false);
                else if (e.Button == MouseButtons.Right) SwatchMenu(p, v).Show(sw, e.Location);
            };
            sw.MouseDoubleClick += delegate (object o, MouseEventArgs e)
            {
                if (e.Button == MouseButtons.Left) Apply(v.ToColor(), true);
            };
            return sw;
        }

        private ContextMenuStrip SwatchMenu(Palette p, VoceColore v)
        {
            ContextMenuStrip m = new ContextMenuStrip();
            m.Items.Add("Applica e OK", null, delegate { Apply(v.ToColor(), true); });
            m.Items.Add("Copia " + v.hex, null, delegate { Clipboard.SetText(v.hex); });
            m.Items.Add(new ToolStripSeparator());
            if (p.IsRecent)
            {
                ToolStripMenuItem addTo = new ToolStripMenuItem("Aggiungi alla palette");
                foreach (Palette dest in palettes)
                {
                    if (dest.IsRecent) continue;
                    Palette d = dest;
                    addTo.DropDownItems.Add(d.Nome, null, delegate { AddTo(d, v.ToColor()); });
                }
                m.Items.Add(addTo);
            }
            else
            {
                m.Items.Add("Rinomina…", null, delegate
                {
                    string n = Prompt.Show(this, "Rinomina colore", "Nome del colore:", v.nome, s);
                    if (n == null) return;
                    v.nome = n.Trim();
                    SaveOrWarn(p);
                    ShowSelected();
                });
                m.Items.Add("Sposta all'inizio", null, delegate
                {
                    p.Colori.Remove(v);
                    p.Colori.Insert(0, v);
                    SaveOrWarn(p);
                    ShowSelected();
                });
            }
            m.Items.Add("Elimina", null, delegate
            {
                p.Colori.Remove(v);
                SaveOrWarn(p);
                ShowSelected();
            });
            m.Closed += delegate { BeginInvoke((Action)m.Dispose); };
            return m;
        }

        private void Apply(Color c, bool pressOk)
        {
            if (ApplyColor == null) return;
            bool ok = ApplyColor(c, pressOk);
            if (!ok)
            {
                MessageBox.Show(this, "Non riesco a scrivere il colore nella finestra Colore.\n" +
                    "Usa \"Diagnosi\" dal menu dell'icona CDV Colori e mandami il file.", "CDV Colori",
                    MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            Palette r = Recenti;
            if (r != null)
            {
                PaletteStore.AddRecent(r, c);
                if (Selected == r) ShowSelected();
            }
        }

        /// <summary>Da chiamare quando il colore arriva dal contagocce.</summary>
        public void NotifyPicked(Color c)
        {
            txtValue.Text = ColorText.ToHex(c);
            Palette r = Recenti;
            if (r != null)
            {
                PaletteStore.AddRecent(r, c);
                if (Selected == r) ShowSelected();
            }
        }

        private void ApplyTyped()
        {
            Color c;
            if (!ColorText.TryParse(txtValue.Text, out c))
            {
                MessageBox.Show(this, "Valore non valido. Esempi: #FF8800  oppure  255,136,0", "CDV Colori",
                    MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }
            Apply(c, false);
        }

        private void AddCurrent()
        {
            Palette p = Selected;
            if (p == null || p.IsRecent || ReadCurrent == null) return;
            Color? cur = ReadCurrent();
            if (!cur.HasValue)
            {
                MessageBox.Show(this, "Non riesco a leggere il colore dalla finestra Colore.", "CDV Colori",
                    MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            AddTo(p, cur.Value);
        }

        private void AddTo(Palette p, Color c)
        {
            string n = Prompt.Show(this, "Aggiungi a \"" + p.Nome + "\"",
                "Nome del colore (RGB " + ColorText.ToRgb(c) + "):", "", s);
            if (n == null) return;
            p.Colori.Add(new VoceColore(n.Trim(), c));
            SaveOrWarn(p);
            cmbPalette.SelectedItem = p;
            ShowSelected();
        }

        private void NewPalette()
        {
            string n = Prompt.Show(this, "Nuova palette", "Nome della palette:", "", s);
            if (string.IsNullOrWhiteSpace(n)) return;
            try
            {
                Palette p = PaletteStore.Create(settings.PaletteDir, n.Trim());
                palettes.Add(p);
                cmbPalette.Items.Add(p);
                cmbPalette.SelectedItem = p;
            }
            catch (Exception ex) { Warn(ex); }
        }

        private void RenamePalette()
        {
            Palette p = Selected;
            if (p == null || p.IsRecent) return;
            string n = Prompt.Show(this, "Rinomina palette", "Nuovo nome:", p.Nome, s);
            if (string.IsNullOrWhiteSpace(n)) return;
            p.Nome = n.Trim();
            SaveOrWarn(p);
            Reload();
        }

        private void DeletePalette()
        {
            Palette p = Selected;
            if (p == null || p.IsRecent) return;
            if (MessageBox.Show(this, "Eliminare la palette \"" + p.Nome + "\"?\n(" + p.FilePath + ")", "CDV Colori",
                    MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return;
            try { File.Delete(p.FilePath); } catch (Exception ex) { Warn(ex); }
            Reload();
        }

        private void ClearRecent()
        {
            Palette r = Recenti;
            if (r == null) return;
            r.Colori.Clear();
            SaveOrWarn(r);
            ShowSelected();
        }

        private void SaveOrWarn(Palette p)
        {
            try { p.Save(); } catch (Exception ex) { Warn(ex); }
        }

        private void Warn(Exception ex)
        {
            Log.Write("Palette: " + ex);
            MessageBox.Show(this, "Operazione non riuscita:\n" + ex.Message, "CDV Colori",
                MessageBoxButtons.OK, MessageBoxIcon.Warning);
        }

        public static void OpenFolder(string dir)
        {
            try { Process.Start("explorer.exe", "\"" + dir + "\""); } catch (Exception ex) { Log.Write(ex.Message); }
        }

        /// <summary>Si mette a destra della finestra Colore, o a sinistra se a destra non c'e' spazio.</summary>
        public void PlaceBeside(ColorDialogTarget t)
        {
            Rectangle d = t.Bounds;
            Rectangle wa = Native.WorkAreaForWindow(t.Hwnd);
            int w = Width;
            int gap = Px(4);
            int x = d.Right + gap;
            if (x + w > wa.Right) x = d.Left - gap - w;
            if (x < wa.Left) x = wa.Right - w;
            int h = Math.Max(Px(300), d.Height);
            int y = d.Top;
            if (y + h > wa.Bottom) y = wa.Bottom - h;
            if (y < wa.Top) y = wa.Top;
            Bounds = new Rectangle(x, y, w, h);
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing) { tip.Dispose(); menuPalette.Dispose(); }
            base.Dispose(disposing);
        }
    }

    /// <summary>Quadratino colore.</summary>
    internal sealed class Swatch : Control
    {
        public readonly VoceColore Voce;
        private bool hot;

        public Swatch(VoceColore v)
        {
            Voce = v;
            SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer |
                     ControlStyles.UserPaint | ControlStyles.StandardClick | ControlStyles.StandardDoubleClick, true);
            Cursor = Cursors.Hand;
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            Graphics g = e.Graphics;
            Rectangle r = new Rectangle(0, 0, Width - 1, Height - 1);
            using (SolidBrush b = new SolidBrush(Voce.ToColor())) g.FillRectangle(b, r);
            using (Pen p = new Pen(hot ? Color.FromArgb(0, 120, 215) : Color.FromArgb(140, 140, 140), hot ? 2f : 1f))
                g.DrawRectangle(p, hot ? new Rectangle(1, 1, Width - 2, Height - 2) : r);
        }

        protected override void OnMouseEnter(EventArgs e) { hot = true; Invalidate(); base.OnMouseEnter(e); }
        protected override void OnMouseLeave(EventArgs e) { hot = false; Invalidate(); base.OnMouseLeave(e); }
    }

    /// <summary>Piccola finestra per chiedere un testo.</summary>
    internal static class Prompt
    {
        public static string Show(IWin32Window owner, string title, string label, string value, float s)
        {
            using (Form f = new Form())
            {
                Func<float, int> px = v => (int)Math.Round(v * s);
                f.Text = title;
                f.FormBorderStyle = FormBorderStyle.FixedDialog;
                f.MinimizeBox = false; f.MaximizeBox = false;
                f.ShowInTaskbar = false;
                f.StartPosition = FormStartPosition.CenterParent;
                f.AutoScaleMode = AutoScaleMode.None;
                f.Font = new Font("Segoe UI", 12f * s, GraphicsUnit.Pixel);
                f.ClientSize = new Size(px(320), px(110));

                Label l = new Label { Text = label, AutoSize = false };
                l.SetBounds(px(10), px(10), px(300), px(20));
                TextBox t = new TextBox { Text = value ?? "" };
                t.SetBounds(px(10), px(34), px(300), px(24));
                Button ok = new Button { Text = "OK", DialogResult = DialogResult.OK };
                ok.SetBounds(px(150), px(72), px(76), px(28));
                Button cancel = new Button { Text = "Annulla", DialogResult = DialogResult.Cancel };
                cancel.SetBounds(px(234), px(72), px(76), px(28));
                f.Controls.AddRange(new Control[] { l, t, ok, cancel });
                f.AcceptButton = ok;
                f.CancelButton = cancel;
                return f.ShowDialog(owner) == DialogResult.OK ? t.Text : null;
            }
        }
    }
}
