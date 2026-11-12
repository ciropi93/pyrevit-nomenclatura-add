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
    /// Ricerca in tutte le palette, gruppi, riordino trascinando, varianti del colore attuale.
    /// </summary>
    internal sealed class PalettePanel : Form
    {
        /// <summary>Applica il colore alla finestra Colore; il bool indica se premere anche OK.</summary>
        public Func<Color, bool, bool> ApplyColor;
        /// <summary>Legge il colore attuale della finestra Colore.</summary>
        public Func<Color?> ReadCurrent;
        /// <summary>Richiesta di estrarre una palette da un'immagine (gestita dal programma).</summary>
        public event Action ExtractRequested;

        private static readonly string[] ModeNames = { "Luminosità", "Saturazione", "Tinta", "Armonie" };

        private readonly Settings settings;
        private readonly float s;
        private List<Palette> palettes = new List<Palette>();

        private readonly ComboBox cmbPalette = new ComboBox();
        private readonly Button btnMenu = new Button();
        private readonly TextBox txtSearch = new TextBox();
        private readonly Label lblVariants = new Label();
        private readonly ComboBox cmbMode = new ComboBox();
        private readonly ComboBox cmbPassi = new ComboBox();
        private readonly VariantStrip variants = new VariantStrip();
        private readonly FlowLayoutPanel grid = new FlowLayoutPanel();
        private readonly Label lblHint = new Label();
        private readonly TextBox txtValue = new TextBox();
        private readonly Button btnApply = new Button();
        private readonly Button btnAdd = new Button();
        private readonly ToolTip tip = new ToolTip();
        private readonly ContextMenuStrip menuPalette = new ContextMenuStrip();
        private readonly ToolStripMenuItem miFolder = new ToolStripMenuItem();
        private readonly Timer poll = new Timer();
        private readonly Timer searchDelay = new Timer();
        private readonly Font boldFont;

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
            boldFont = new Font(Font, FontStyle.Bold);

            cmbPalette.DropDownStyle = ComboBoxStyle.DropDownList;
            cmbPalette.SelectedIndexChanged += delegate
            {
                if (txtSearch.Text.Length > 0) txtSearch.Text = ""; // la scelta di una palette chiude la ricerca
                ShowSelected();
            };

            btnMenu.Text = "…";
            btnMenu.Click += delegate { menuPalette.Show(btnMenu, new Point(0, btnMenu.Height)); };
            tip.SetToolTip(btnMenu, "Gestione palette");

            txtSearch.HandleCreated += delegate { Native.SetCueBanner(txtSearch, "Cerca in tutte le palette (nome, gruppo o #HEX)"); };
            searchDelay.Interval = 250;
            searchDelay.Tick += delegate { searchDelay.Stop(); ShowSelected(); };
            txtSearch.TextChanged += delegate { searchDelay.Stop(); searchDelay.Start(); };
            txtSearch.KeyDown += delegate (object o, KeyEventArgs e)
            {
                if (e.KeyCode == Keys.Escape) { e.SuppressKeyPress = true; txtSearch.Text = ""; }
            };

            lblVariants.Text = "Varianti";
            lblVariants.AutoSize = false;
            lblVariants.TextAlign = ContentAlignment.MiddleLeft;
            lblVariants.ForeColor = SystemColors.GrayText;
            cmbMode.DropDownStyle = ComboBoxStyle.DropDownList;
            cmbMode.Items.AddRange(ModeNames);
            cmbMode.SelectedIndex = settings.variantiModo;
            tip.SetToolTip(cmbMode, "Luminosità: più scuro ← → più chiaro\nSaturazione: grigio ← → pieno\n" +
                "Tinta: ±10° per passo\nArmonie: complementare, analoghi, triade, complementari divisi");
            cmbPassi.DropDownStyle = ComboBoxStyle.DropDownList;
            for (int i = ColorText.MinPassi; i <= ColorText.MaxPassi; i++) cmbPassi.Items.Add(i.ToString());
            cmbPassi.SelectedIndex = settings.variantiPassi - ColorText.MinPassi;
            tip.SetToolTip(cmbPassi, "Varianti per lato");
            cmbMode.SelectedIndexChanged += delegate { ModeChanged(); };
            cmbPassi.SelectedIndexChanged += delegate { ModeChanged(); };
            variants.SetMode((VariantMode)settings.variantiModo, settings.variantiPassi);
            cmbPassi.Enabled = settings.variantiModo != (int)VariantMode.Armonie;
            variants.VariantClicked += delegate (Color c, bool ok) { Apply(c, ok); };
            variants.VariantRightClicked += delegate (Color c, Point at) { VariantMenu(c).Show(variants, at); };

            grid.AutoScroll = true;
            grid.WrapContents = true;
            grid.BackColor = SystemColors.Window;
            grid.BorderStyle = BorderStyle.FixedSingle;
            grid.Padding = new Padding(Px(3));
            grid.AllowDrop = true;
            grid.DragOver += delegate (object o, DragEventArgs e) { e.Effect = CanDrop(e) ? DragDropEffects.Move : DragDropEffects.None; };
            grid.DragDrop += delegate (object o, DragEventArgs e) { DropAt(e, null, null); };

            lblHint.Text = "Clic: applica  ·  Doppio clic: applica e OK  ·  Trascina per riordinare";
            lblHint.ForeColor = SystemColors.GrayText;
            lblHint.AutoSize = false;
            lblHint.AutoEllipsis = true;

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
            ToolStripItem miExtract = menuPalette.Items.Add("Estrai palette da immagine…", null,
                delegate { if (ExtractRequested != null) ExtractRequested(); });
            menuPalette.Items.Add(new ToolStripSeparator());
            menuPalette.Items.Add("Svuota recenti", null, delegate { ClearRecent(); });
            menuPalette.Items.Add("Ripristina palette di base", null, delegate { RestoreBase(); });
            menuPalette.Items.Add(new ToolStripSeparator());
            miFolder.Enabled = false;
            menuPalette.Items.Add(miFolder);
            menuPalette.Items.Add("Cambia cartella palette…", null, delegate { ChangeFolder(); });
            menuPalette.Items.Add("Usa cartella personale", null, delegate { SetFolder(""); });
            menuPalette.Items.Add("Apri cartella palette", null, delegate { OpenFolder(settings.PaletteDir); });
            menuPalette.Items.Add("Ricarica", null, delegate { Reload(); });
            menuPalette.Opening += delegate
            {
                miFolder.Text = "Cartella: " + ShortPath(settings.PaletteDir);
                miExtract.Visible = ExtractRequested != null;
            };

            // il pannello segue il colore della finestra Colore, comunque venga cambiato
            poll.Interval = 300;
            poll.Tick += delegate { SyncFromDialog(); };

            Controls.AddRange(new Control[] { cmbPalette, btnMenu, txtSearch, lblVariants, cmbMode, cmbPassi, variants,
                grid, lblHint, txtValue, btnApply, btnAdd });
            ClientSize = new Size(Px(260), Px(500));
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
            int y = m;
            btnMenu.SetBounds(w - m - h, y, h, h);
            cmbPalette.SetBounds(m, y + Px(1), w - 2 * m - h - Px(4), h);
            y += h + Px(6);
            txtSearch.SetBounds(m, y, w - 2 * m, h);
            y += h + Px(8);
            int passiW = Px(44), modeW = Px(110);
            cmbPassi.SetBounds(w - m - passiW, y, passiW, h);
            cmbMode.SetBounds(w - m - passiW - Px(4) - modeW, y, modeW, h);
            lblVariants.SetBounds(m, y, w - 2 * m - passiW - modeW - Px(8), h);
            y += h + Px(3);
            variants.SetBounds(m, y, w - 2 * m, Px(30));
            y += Px(30) + Px(8);

            int bottom = ClientSize.Height - m;
            btnAdd.SetBounds(m, bottom - h, w - 2 * m, h);
            bottom -= h + Px(4);
            int bw = Px(64);
            btnApply.SetBounds(w - m - bw, bottom - h, bw, h);
            txtValue.SetBounds(m, bottom - h + Px(2), w - 2 * m - bw - Px(4), h);
            bottom -= h + Px(4);
            lblHint.SetBounds(m, bottom - Px(18), w - 2 * m, Px(18));
            bottom -= Px(20);
            grid.SetBounds(m, y, w - 2 * m, Math.Max(Px(60), bottom - y));
        }

        // ------------------------------------------------------------------ palette e griglia

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

        private bool Searching { get { return txtSearch.Text.Trim().Length > 0; } }

        private void ClearGrid()
        {
            Control[] old = new Control[grid.Controls.Count];
            grid.Controls.CopyTo(old, 0);
            grid.Controls.Clear();
            foreach (Control c in old) c.Dispose();
        }

        private void ShowSelected()
        {
            grid.SuspendLayout();
            ClearGrid();
            if (Searching) ShowSearch(txtSearch.Text.Trim());
            else ShowPalette();
            grid.ResumeLayout();
        }

        private void ShowPalette()
        {
            Palette p = Selected;
            if (p == null) return;
            if (!p.IsRecent && settings.ultimaPalette != p.Nome)
            {
                settings.ultimaPalette = p.Nome;
                settings.Save();
            }
            btnAdd.Enabled = !p.IsRecent;
            if (p.Colori.Count == 0)
            {
                AddNote(p.IsRecent
                    ? "I colori che applichi da qui\ncompariranno in questo elenco."
                    : "Palette vuota: imposta un colore\nnella finestra e premi \"+ Aggiungi\".");
                return;
            }
            if (!p.HasGroups)
            {
                foreach (VoceColore v in p.Colori) grid.Controls.Add(MakeSwatch(p, v, false));
                return;
            }
            foreach (KeyValuePair<string, List<VoceColore>> kv in p.Grouped())
            {
                AddHeader(kv.Key == "" ? "Altri" : kv.Key, p, kv.Key);
                foreach (VoceColore v in kv.Value) grid.Controls.Add(MakeSwatch(p, v, false));
            }
        }

        private void ShowSearch(string q)
        {
            btnAdd.Enabled = Selected != null && !Selected.IsRecent;
            string qq = q.TrimStart('#').ToLowerInvariant();
            int found = 0;
            foreach (Palette p in palettes)
            {
                if (p.IsRecent) continue;
                List<VoceColore> hits = p.Colori.FindAll(v =>
                    (v.nome ?? "").ToLowerInvariant().Contains(qq) ||
                    (v.gruppo ?? "").ToLowerInvariant().Contains(qq) ||
                    (v.hex ?? "").TrimStart('#').ToLowerInvariant().Contains(qq));
                if (hits.Count == 0) continue;
                AddHeader(p.Nome + "  (" + hits.Count + ")", null, null);
                foreach (VoceColore v in hits) grid.Controls.Add(MakeSwatch(p, v, true));
                found += hits.Count;
            }
            if (found == 0) AddNote("Nessun colore trovato per \"" + q + "\".");
        }

        private void AddNote(string text)
        {
            Label l = new Label();
            l.AutoSize = true;
            l.ForeColor = SystemColors.GrayText;
            l.Text = text;
            grid.Controls.Add(l);
        }

        /// <summary>Intestazione di gruppo a tutta larghezza (si puo' trascinarci sopra un colore).</summary>
        private void AddHeader(string text, Palette p, string gruppo)
        {
            Label l = new Label();
            l.AutoSize = false;
            l.Text = text;
            l.Font = boldFont;
            l.ForeColor = SystemColors.ControlDarkDark;
            l.Margin = new Padding(Px(2), grid.Controls.Count == 0 ? Px(2) : Px(8), Px(2), Px(1));
            l.Size = new Size(Math.Max(Px(60), grid.ClientSize.Width - grid.Padding.Horizontal - SystemInformation.VerticalScrollBarWidth - Px(4)), Px(18));
            if (p != null)
            {
                l.AllowDrop = true;
                l.DragOver += delegate (object o, DragEventArgs e) { e.Effect = CanDrop(e) ? DragDropEffects.Move : DragDropEffects.None; };
                l.DragDrop += delegate (object o, DragEventArgs e) { DropAt(e, null, gruppo); };
            }
            grid.Controls.Add(l);
            grid.SetFlowBreak(l, true);
        }

        private Swatch MakeSwatch(Palette p, VoceColore v, bool inSearch)
        {
            Swatch sw = new Swatch(p, v);
            int size = Px(26);
            sw.Size = new Size(size, size);
            sw.Margin = new Padding(Px(2));
            string desc = ColorText.Describe(v);
            if (!string.IsNullOrEmpty(v.gruppo)) desc += "\nGruppo: " + v.gruppo;
            if (inSearch) desc += "\nPalette: " + p.Nome;
            tip.SetToolTip(sw, desc);
            sw.MouseClick += delegate (object o, MouseEventArgs e)
            {
                if (e.Button == MouseButtons.Left) Apply(v.ToColor(), false);
                else if (e.Button == MouseButtons.Right) SwatchMenu(p, v).Show(sw, e.Location);
            };
            sw.MouseDoubleClick += delegate (object o, MouseEventArgs e)
            {
                if (e.Button == MouseButtons.Left) Apply(v.ToColor(), true);
            };
            if (!inSearch && !p.IsRecent)
            {
                sw.CanDrag = true;
                sw.AllowDrop = true;
                sw.DragOver += delegate (object o, DragEventArgs e) { e.Effect = CanDrop(e) ? DragDropEffects.Move : DragDropEffects.None; };
                sw.DragDrop += delegate (object o, DragEventArgs e)
                {
                    Point pt = sw.PointToClient(new Point(e.X, e.Y));
                    DropAt(e, new KeyValuePair<VoceColore, bool>(v, pt.X > sw.Width / 2), null);
                };
            }
            return sw;
        }

        // ------------------------------------------------------------------ trascinamento

        private bool CanDrop(DragEventArgs e)
        {
            Swatch src = e.Data.GetData(typeof(Swatch)) as Swatch;
            return src != null && !Searching && src.Palette == Selected && !src.Palette.IsRecent;
        }

        /// <summary>
        /// Sposta il colore trascinato: prima o dopo un altro colore (che ne da' anche il gruppo),
        /// in fondo a un gruppo (intestazione), oppure in fondo alla palette (spazio vuoto).
        /// </summary>
        private void DropAt(DragEventArgs e, KeyValuePair<VoceColore, bool>? target, string gruppo)
        {
            if (!CanDrop(e)) return;
            Swatch src = (Swatch)e.Data.GetData(typeof(Swatch));
            Palette p = src.Palette;
            VoceColore v = src.Voce;
            p.Normalize();
            List<VoceColore> list = p.Colori;
            if (target.HasValue && target.Value.Key == v) return;
            list.Remove(v);
            if (target.HasValue)
            {
                VoceColore t = target.Value.Key;
                v.gruppo = t.gruppo ?? "";
                int idx = list.IndexOf(t);
                list.Insert(target.Value.Value ? idx + 1 : idx, v);
            }
            else if (gruppo != null)
            {
                v.gruppo = gruppo;
                int last = list.FindLastIndex(x => (x.gruppo ?? "") == gruppo);
                list.Insert(last < 0 ? list.Count : last + 1, v);
            }
            else
            {
                list.Add(v);
            }
            p.Normalize();
            SaveOrWarn(p);
            ShowSelected();
        }

        // ------------------------------------------------------------------ varianti

        private void ModeChanged()
        {
            if (cmbMode.SelectedIndex < 0 || cmbPassi.SelectedIndex < 0) return;
            settings.variantiModo = cmbMode.SelectedIndex;
            settings.variantiPassi = cmbPassi.SelectedIndex + ColorText.MinPassi;
            settings.Save();
            cmbPassi.Enabled = settings.variantiModo != (int)VariantMode.Armonie;
            variants.SetMode((VariantMode)settings.variantiModo, settings.variantiPassi);
            SyncFromDialog();
        }

        /// <summary>
        /// Legge il colore dalla finestra Colore. Se e' una delle varianti mostrate la evidenzia,
        /// altrimenti lo usa come nuovo colore base (cosi' scegliendo una variante la riga non "scappa").
        /// </summary>
        private void SyncFromDialog()
        {
            if (ReadCurrent == null) return;
            Color? cur = ReadCurrent();
            if (!cur.HasValue) return;
            if (variants.Contains(cur.Value)) variants.MarkSelected(cur.Value);
            else variants.SetBase(cur.Value);
        }

        protected override void OnVisibleChanged(EventArgs e)
        {
            base.OnVisibleChanged(e);
            if (Visible) { SyncFromDialog(); poll.Start(); }
            else poll.Stop();
        }

        private ContextMenuStrip VariantMenu(Color c)
        {
            ContextMenuStrip m = new ContextMenuStrip();
            string hex = ColorText.ToHex(c);
            m.Items.Add("Applica e OK", null, delegate { Apply(c, true); });
            m.Items.Add("Usa come colore base", null, delegate { variants.SetBase(c); });
            m.Items.Add("Copia " + hex, null, delegate { Clipboard.SetText(hex); });
            m.Items.Add(AddToMenu(c));
            m.Closed += delegate { BeginInvoke((Action)m.Dispose); };
            return m;
        }

        private ToolStripMenuItem AddToMenu(Color c)
        {
            ToolStripMenuItem addTo = new ToolStripMenuItem("Aggiungi alla palette");
            foreach (Palette dest in palettes)
            {
                if (dest.IsRecent) continue;
                Palette d = dest;
                addTo.DropDownItems.Add(d.Nome, null, delegate { AddTo(d, c); });
            }
            return addTo;
        }

        // ------------------------------------------------------------------ menu del colore

        private ContextMenuStrip SwatchMenu(Palette p, VoceColore v)
        {
            ContextMenuStrip m = new ContextMenuStrip();
            m.Items.Add("Applica e OK", null, delegate { Apply(v.ToColor(), true); });
            m.Items.Add("Usa come base per le varianti", null, delegate { variants.SetBase(v.ToColor()); });
            m.Items.Add("Copia " + v.hex, null, delegate { Clipboard.SetText(v.hex); });
            m.Items.Add(new ToolStripSeparator());
            if (p.IsRecent)
            {
                m.Items.Add(AddToMenu(v.ToColor()));
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
                m.Items.Add(GroupMenu(p, v));
                if (Searching) m.Items.Add("Mostra nella palette", null, delegate
                {
                    cmbPalette.SelectedItem = p; // chiude anche la ricerca
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

        private ToolStripMenuItem GroupMenu(Palette p, VoceColore v)
        {
            ToolStripMenuItem g = new ToolStripMenuItem("Sposta nel gruppo");
            Action<string> move = delegate (string gruppo)
            {
                p.Colori.Remove(v);
                v.gruppo = gruppo;
                int last = p.Colori.FindLastIndex(x => (x.gruppo ?? "") == gruppo);
                p.Colori.Insert(last < 0 ? p.Colori.Count : last + 1, v);
                p.Normalize();
                SaveOrWarn(p);
                ShowSelected();
            };
            foreach (string name in p.GroupNames())
            {
                string n = name;
                ToolStripMenuItem it = new ToolStripMenuItem(n, null, delegate { move(n); });
                it.Checked = n == v.gruppo;
                g.DropDownItems.Add(it);
            }
            if (g.DropDownItems.Count > 0) g.DropDownItems.Add(new ToolStripSeparator());
            g.DropDownItems.Add("Nuovo gruppo…", null, delegate
            {
                string n = Prompt.Show(this, "Nuovo gruppo", "Nome del gruppo:", "", s);
                if (!string.IsNullOrWhiteSpace(n)) move(n.Trim());
            });
            if (!string.IsNullOrEmpty(v.gruppo))
                g.DropDownItems.Add("Nessun gruppo", null, delegate { move(""); });
            return g;
        }

        // ------------------------------------------------------------------ applicazione

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
            AddRecent(c);
        }

        private void AddRecent(Color c)
        {
            Palette r = Recenti;
            if (r == null) return;
            PaletteStore.AddRecent(r, c);
            if (Selected == r && !Searching) ShowSelected();
        }

        /// <summary>Da chiamare quando il colore arriva dal contagocce.</summary>
        public void NotifyPicked(Color c)
        {
            txtValue.Text = ColorText.ToHex(c);
            AddRecent(c);
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
            txtSearch.Text = "";
            cmbPalette.SelectedItem = p;
            ShowSelected();
        }

        // ------------------------------------------------------------------ gestione palette

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

        /// <summary>Seleziona la palette con questo nome (dopo averla creata da fuori, es. da un'immagine).</summary>
        public void SelectPalette(string nome)
        {
            settings.ultimaPalette = nome;
            cmbPalette.SelectedIndex = -1;
            Reload();
        }

        private void RenamePalette()
        {
            Palette p = Selected;
            if (p == null || p.IsRecent) return;
            string n = Prompt.Show(this, "Rinomina palette", "Nuovo nome:", p.Nome, s);
            if (string.IsNullOrWhiteSpace(n)) return;
            p.Nome = n.Trim();
            SaveOrWarn(p);
            SelectPalette(p.Nome);
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

        private void RestoreBase()
        {
            if (MessageBox.Show(this, "Ripristinare la palette \"Base\" con i colori originali?\n" +
                    "Le modifiche fatte alla palette Base andranno perse.", "CDV Colori",
                    MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return;
            try
            {
                Palette p = PaletteStore.CreaBase(settings.PaletteDir);
                SelectPalette(p.Nome);
            }
            catch (Exception ex) { Warn(ex); }
        }

        private void ClearRecent()
        {
            Palette r = Recenti;
            if (r == null) return;
            r.Colori.Clear();
            SaveOrWarn(r);
            ShowSelected();
        }

        private void ChangeFolder()
        {
            using (FolderBrowserDialog d = new FolderBrowserDialog())
            {
                d.Description = "Cartella delle palette (anche di rete, per condividerle con i colleghi)";
                d.SelectedPath = settings.PaletteDir;
                d.ShowNewFolderButton = true;
                if (d.ShowDialog(this) != DialogResult.OK) return;
                SetFolder(d.SelectedPath);
            }
        }

        private void SetFolder(string path)
        {
            settings.cartellaPalette = path ?? "";
            settings.Save();
            cmbPalette.SelectedIndex = -1;
            Reload();
        }

        private static string ShortPath(string p)
        {
            return p.Length <= 48 ? p : "…" + p.Substring(p.Length - 47);
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
            int h = Math.Max(Px(520), d.Height);
            if (h > wa.Height) h = wa.Height;
            int y = d.Top;
            if (y + h > wa.Bottom) y = wa.Bottom - h;
            if (y < wa.Top) y = wa.Top;
            Bounds = new Rectangle(x, y, w, h);
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing) { boldFont.Dispose(); poll.Dispose(); searchDelay.Dispose(); tip.Dispose(); menuPalette.Dispose(); }
            base.Dispose(disposing);
        }
    }

    /// <summary>Quadratino colore (trascinabile per riordinare).</summary>
    internal sealed class Swatch : Control
    {
        public readonly Palette Palette;
        public readonly VoceColore Voce;
        public bool CanDrag;
        private bool hot;
        private Point downAt;
        private bool down;

        public Swatch(Palette p, VoceColore v)
        {
            Palette = p;
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

        protected override void OnMouseDown(MouseEventArgs e)
        {
            if (e.Button == MouseButtons.Left) { down = true; downAt = e.Location; }
            base.OnMouseDown(e);
        }

        protected override void OnMouseMove(MouseEventArgs e)
        {
            base.OnMouseMove(e);
            if (!down || !CanDrag || e.Button != MouseButtons.Left) return;
            Size ds = SystemInformation.DragSize;
            if (Math.Abs(e.X - downAt.X) > ds.Width || Math.Abs(e.Y - downAt.Y) > ds.Height)
            {
                down = false;
                DoDragDrop(this, DragDropEffects.Move);
            }
        }

        protected override void OnMouseUp(MouseEventArgs e)
        {
            down = false;
            base.OnMouseUp(e);
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
