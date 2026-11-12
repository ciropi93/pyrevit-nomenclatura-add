using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace CDVColori
{
    /// <summary>
    /// "Estrai palette da immagine": apri un file, incolla dagli appunti o cattura una zona dello schermo;
    /// il programma trova i colori, li mostra sull'immagine con un numero e li salva in una palette.
    /// </summary>
    internal sealed class ImagePaletteForm : Form
    {
        /// <summary>Palette creata o aggiornata (nome), per selezionarla nel pannello.</summary>
        public event Action<string> PaletteSaved;

        private readonly Settings settings;
        private readonly float s;
        private Bitmap image;
        private string imageName = "";
        private ExtractResult result;
        private readonly List<string> names = new List<string>();

        private readonly Button btnOpen = new Button(), btnPaste = new Button(), btnScreen = new Button();
        private readonly NumericUpDown numMax = new NumericUpDown();
        private readonly TrackBar trkMerge = new TrackBar();
        private readonly Label lblMerge = new Label();
        private readonly CheckBox chkWhite = new CheckBox(), chkBlack = new CheckBox();
        private readonly ComboBox cmbSort = new ComboBox();
        private readonly PictureBox pic = new PictureBox();
        private readonly ListView list = new ListView();
        private readonly ImageList swatches = new ImageList();
        private readonly Label lblInfo = new Label();
        private readonly TextBox txtName = new TextBox();
        private readonly Button btnCreate = new Button(), btnAppend = new Button(), btnClose = new Button();
        private readonly ComboBox cmbTarget = new ComboBox();
        private readonly Timer rerun = new Timer();

        public ImagePaletteForm(Settings settings)
        {
            this.settings = settings;
            Native.POINT cp;
            Native.GetCursorPos(out cp);
            s = Native.ScaleForPoint(cp.X, cp.Y);
            Text = "CDV Colori – Estrai palette da immagine";
            AutoScaleMode = AutoScaleMode.None;
            Font = new Font("Segoe UI", 12f * s, GraphicsUnit.Pixel);
            StartPosition = FormStartPosition.CenterScreen;
            ShowInTaskbar = true;
            Size = new Size(Px(1000), Px(640));
            MinimumSize = new Size(Px(720), Px(460));
            KeyPreview = true;

            // ---- barra in alto
            FlowLayoutPanel top = new FlowLayoutPanel();
            top.Dock = DockStyle.Top;
            top.AutoSize = true;
            top.Padding = new Padding(Px(6));
            top.WrapContents = true;
            Setup(btnOpen, "Apri immagine…", delegate { OpenFile(); });
            Setup(btnPaste, "Incolla (Ctrl+V)", delegate { PasteImage(); });
            Setup(btnScreen, "Cattura zona dello schermo", delegate { CaptureScreen(); });
            top.Controls.AddRange(new Control[] { btnOpen, btnPaste, btnScreen });

            Label lMax = SmallLabel("Max colori");
            numMax.Minimum = 2; numMax.Maximum = 200; numMax.Value = 60;
            numMax.Width = Px(60);
            numMax.Margin = new Padding(Px(2), Px(5), Px(10), Px(2));
            numMax.ValueChanged += delegate { Schedule(); };

            Label lMerge = SmallLabel("Fusione");
            trkMerge.Minimum = 1; trkMerge.Maximum = 15; trkMerge.Value = 3;
            trkMerge.TickStyle = TickStyle.None;
            trkMerge.Width = Px(110);
            trkMerge.AutoSize = false;
            trkMerge.Height = Px(28);
            trkMerge.ValueChanged += delegate { lblMerge.Text = trkMerge.Value.ToString(); Schedule(); };
            lblMerge.AutoSize = true;
            lblMerge.Text = "3";
            lblMerge.Margin = new Padding(0, Px(8), Px(10), 0);
            ToolTip tt = new ToolTip();
            tt.SetToolTip(trkMerge, "Colori più simili di questa soglia (Delta E) diventano uno solo.\nPiù basso = più colori distinti.");

            chkWhite.Text = "Ignora bianco"; chkWhite.Checked = true; chkWhite.AutoSize = true;
            chkWhite.Margin = new Padding(Px(4), Px(7), Px(4), 0);
            chkWhite.CheckedChanged += delegate { Schedule(); };
            chkBlack.Text = "Ignora nero"; chkBlack.AutoSize = true;
            chkBlack.Margin = new Padding(Px(4), Px(7), Px(10), 0);
            chkBlack.CheckedChanged += delegate { Schedule(); };

            cmbSort.DropDownStyle = ComboBoxStyle.DropDownList;
            cmbSort.Items.AddRange(new object[] { "Ordina per area", "Ordina per tinta" });
            cmbSort.SelectedIndex = 0;
            cmbSort.Width = Px(130);
            cmbSort.Margin = new Padding(Px(4), Px(4), Px(4), 0);
            cmbSort.SelectedIndexChanged += delegate { Schedule(); };
            top.Controls.AddRange(new Control[] { lMax, numMax, lMerge, trkMerge, lblMerge, chkWhite, chkBlack, cmbSort });

            // ---- in basso
            TableLayoutPanel bottom = new TableLayoutPanel();
            bottom.Dock = DockStyle.Bottom;
            bottom.AutoSize = true;
            bottom.Padding = new Padding(Px(6));
            bottom.ColumnCount = 7;
            bottom.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            bottom.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, Px(200)));
            bottom.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            bottom.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, Px(30)));
            bottom.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, Px(170)));
            bottom.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            bottom.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            Label lName = SmallLabel("Nome palette");
            txtName.Dock = DockStyle.Fill;
            Setup(btnCreate, "Crea palette", delegate { Save(null); });
            cmbTarget.DropDownStyle = ComboBoxStyle.DropDownList;
            cmbTarget.Dock = DockStyle.Fill;
            Setup(btnAppend, "Aggiungi a questa palette", delegate { Save(cmbTarget.SelectedItem as Palette); });
            tt.SetToolTip(btnAppend, "Aggiunge i colori spuntati in fondo alla palette scelta.\n" +
                "Se la palette ha gruppi, i colori vanno nel gruppo col nome scritto a sinistra.");
            tt.SetToolTip(list, "Spunta i colori da salvare. Seleziona una riga per vedere dove si trova il colore.\n" +
                "F2 o clic sul nome per rinominarlo.");
            Setup(btnClose, "Chiudi", delegate { Close(); });
            btnClose.Anchor = AnchorStyles.Right;
            bottom.Controls.Add(lName, 0, 0);
            bottom.Controls.Add(txtName, 1, 0);
            bottom.Controls.Add(btnCreate, 2, 0);
            bottom.Controls.Add(new Label { AutoSize = false, Width = 1 }, 3, 0);
            bottom.Controls.Add(cmbTarget, 4, 0);
            bottom.Controls.Add(btnAppend, 5, 0);
            bottom.Controls.Add(btnClose, 6, 0);

            lblInfo.Dock = DockStyle.Bottom;
            lblInfo.Height = Px(22);
            lblInfo.Padding = new Padding(Px(8), 0, 0, 0);
            lblInfo.ForeColor = SystemColors.GrayText;
            lblInfo.Text = "Apri un'immagine, incollala o cattura una zona dello schermo.";

            // ---- centro: immagine | elenco
            SplitContainer split = new SplitContainer();
            split.Dock = DockStyle.Fill;
            pic.Dock = DockStyle.Fill;
            pic.SizeMode = PictureBoxSizeMode.Zoom;
            pic.BackColor = Color.FromArgb(235, 235, 235);
            pic.Paint += PaintMarkers;
            split.Panel1.Controls.Add(pic);

            swatches.ColorDepth = ColorDepth.Depth32Bit;
            swatches.ImageSize = new Size(Px(22), Px(18));
            list.Dock = DockStyle.Fill;
            list.View = View.Details;
            list.CheckBoxes = true;
            list.FullRowSelect = true;
            list.LabelEdit = true;
            list.HideSelection = false;
            list.SmallImageList = swatches;
            list.Columns.Add("Nome (F2 per rinominare)", Px(190));
            list.Columns.Add("HEX", Px(80));
            list.Columns.Add("RGB", Px(95));
            list.Columns.Add("Area", Px(55), HorizontalAlignment.Right);
            list.AfterLabelEdit += delegate (object o, LabelEditEventArgs e)
            {
                if (e.Label != null && e.Item >= 0 && e.Item < names.Count) names[e.Item] = e.Label.Trim();
            };
            list.SelectedIndexChanged += delegate { pic.Invalidate(); };
            split.Panel2.Controls.Add(list);

            Controls.Add(split);
            Controls.Add(lblInfo);
            Controls.Add(bottom);
            Controls.Add(top);
            Shown += delegate { split.SplitterDistance = (int)(split.Width * 0.55); };

            rerun.Interval = 300;
            rerun.Tick += delegate { rerun.Stop(); RunExtraction(); };

            AllowDrop = true;
            DragEnter += delegate (object o, DragEventArgs e)
            {
                e.Effect = e.Data.GetDataPresent(DataFormats.FileDrop) ? DragDropEffects.Copy : DragDropEffects.None;
            };
            DragDrop += delegate (object o, DragEventArgs e)
            {
                string[] files = e.Data.GetData(DataFormats.FileDrop) as string[];
                if (files != null && files.Length > 0) LoadFile(files[0]);
            };

            LoadTargets();
            UpdateButtons();
        }

        private int Px(float v) { return (int)Math.Round(v * s); }

        private void Setup(Button b, string text, EventHandler click)
        {
            b.Text = text;
            b.AutoSize = true;
            b.AutoSizeMode = AutoSizeMode.GrowAndShrink;
            b.Padding = new Padding(Px(6), Px(2), Px(6), Px(2));
            b.Click += click;
        }

        private Label SmallLabel(string text)
        {
            Label l = new Label();
            l.Text = text;
            l.AutoSize = true;
            l.Margin = new Padding(Px(8), Px(8), Px(2), 0);
            return l;
        }

        protected override bool ProcessCmdKey(ref Message msg, Keys keyData)
        {
            if (keyData == (Keys.Control | Keys.V) && !(ActiveControl is TextBox)) { PasteImage(); return true; }
            if (keyData == Keys.Escape) { Close(); return true; }
            return base.ProcessCmdKey(ref msg, keyData);
        }

        // ------------------------------------------------------------------ sorgenti

        private void OpenFile()
        {
            using (OpenFileDialog d = new OpenFileDialog())
            {
                d.Title = "Immagine da cui estrarre i colori";
                d.Filter = "Immagini|*.png;*.jpg;*.jpeg;*.bmp;*.gif;*.tif;*.tiff|Tutti i file|*.*";
                if (d.ShowDialog(this) == DialogResult.OK) LoadFile(d.FileName);
            }
        }

        private void LoadFile(string path)
        {
            try
            {
                // copia in memoria: il file non resta bloccato
                using (Image img = Image.FromFile(path)) SetImage(new Bitmap(img), Path.GetFileNameWithoutExtension(path));
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, "Immagine non leggibile:\n" + ex.Message, "CDV Colori", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            }
        }

        private void PasteImage()
        {
            try
            {
                if (Clipboard.ContainsImage())
                {
                    using (Image img = Clipboard.GetImage()) SetImage(new Bitmap(img), "Appunti");
                    return;
                }
                if (Clipboard.ContainsFileDropList() && Clipboard.GetFileDropList().Count > 0)
                {
                    LoadFile(Clipboard.GetFileDropList()[0]);
                    return;
                }
                MessageBox.Show(this, "Negli appunti non c'è un'immagine.", "CDV Colori", MessageBoxButtons.OK, MessageBoxIcon.Information);
            }
            catch (Exception ex) { Log.Write("Incolla immagine: " + ex.Message); }
        }

        private void CaptureScreen()
        {
            FormWindowState prev = WindowState;
            Hide();
            Application.DoEvents();
            System.Threading.Thread.Sleep(250); // lascia sparire la finestra prima della cattura
            Bitmap shot = null;
            try { shot = ScreenRegion.CaptureRegion(); }
            catch (Exception ex) { Log.Write("Cattura schermo: " + ex.Message); }
            Show();
            WindowState = prev;
            Activate();
            if (shot != null) SetImage(shot, "Schermo");
        }

        private void SetImage(Bitmap bmp, string name)
        {
            Image old = pic.Image;
            image = bmp;
            imageName = name;
            pic.Image = bmp;
            if (old != null) old.Dispose();
            if (string.IsNullOrWhiteSpace(txtName.Text) || txtName.Tag as string == "auto")
            {
                txtName.Text = name;
                txtName.Tag = "auto";
            }
            RunExtraction();
        }

        // ------------------------------------------------------------------ estrazione

        private void Schedule()
        {
            if (image == null) return;
            rerun.Stop();
            rerun.Start();
        }

        private void RunExtraction()
        {
            if (image == null) return;
            Cursor = Cursors.WaitCursor;
            try
            {
                int w = image.Width, h = image.Height;
                int[] px = Pixels(image);
                ExtractOptions o = new ExtractOptions();
                o.MaxColors = (int)numMax.Value;
                o.MergeDeltaE = trkMerge.Value;
                o.IgnoreWhite = chkWhite.Checked;
                o.IgnoreBlack = chkBlack.Checked;
                o.SortByHue = cmbSort.SelectedIndex == 1;
                result = ImagePalette.Extract(px, w, h, o);
                FillList();
                lblInfo.Text = result.Colors.Count + " colori trovati" +
                    (result.UsedFallback
                        ? "  ·  immagine senza zone piatte (foto o sfumature): colori medi per gruppi simili"
                        : "  ·  i numeri sull'immagine indicano dove si trova ogni colore");
            }
            catch (Exception ex)
            {
                Log.Write("Estrazione: " + ex);
                lblInfo.Text = "Estrazione non riuscita: " + ex.Message;
            }
            finally { Cursor = Cursors.Default; }
            UpdateButtons();
            pic.Invalidate();
        }

        private static int[] Pixels(Bitmap bmp)
        {
            Rectangle r = new Rectangle(0, 0, bmp.Width, bmp.Height);
            using (Bitmap b32 = bmp.Clone(r, PixelFormat.Format32bppArgb))
            {
                BitmapData d = b32.LockBits(r, ImageLockMode.ReadOnly, PixelFormat.Format32bppArgb);
                try
                {
                    int[] px = new int[bmp.Width * bmp.Height];
                    for (int y = 0; y < bmp.Height; y++)
                        Marshal.Copy(IntPtr.Add(d.Scan0, y * d.Stride), px, y * bmp.Width, bmp.Width);
                    // pixel trasparenti = sfondo bianco
                    for (int i = 0; i < px.Length; i++) if (((px[i] >> 24) & 0xFF) < 128) px[i] = unchecked((int)0xFFFFFFFF);
                    return px;
                }
                finally { b32.UnlockBits(d); }
            }
        }

        private void FillList()
        {
            list.BeginUpdate();
            list.Items.Clear();
            foreach (Image im in swatches.Images) im.Dispose();
            swatches.Images.Clear();
            names.Clear();
            for (int i = 0; i < result.Colors.Count; i++)
            {
                FoundColor f = result.Colors[i];
                Bitmap sw = new Bitmap(swatches.ImageSize.Width, swatches.ImageSize.Height);
                using (Graphics g = Graphics.FromImage(sw))
                {
                    using (SolidBrush b = new SolidBrush(f.Color)) g.FillRectangle(b, 0, 0, sw.Width, sw.Height);
                    g.DrawRectangle(Pens.Gray, 0, 0, sw.Width - 1, sw.Height - 1);
                }
                swatches.Images.Add(sw);
                string name = "Colore " + (i + 1);
                names.Add(name);
                ListViewItem it = new ListViewItem(name, i);
                it.Checked = true;
                it.SubItems.Add(ColorText.ToHex(f.Color));
                it.SubItems.Add(ColorText.ToRgb(f.Color));
                it.SubItems.Add(f.AreaPercent < 0.1 ? "<0,1%" : f.AreaPercent.ToString("0.0") + "%");
                list.Items.Add(it);
            }
            list.EndUpdate();
        }

        /// <summary>Numeri sull'immagine nei punti dove sono stati trovati i colori.</summary>
        private void PaintMarkers(object sender, PaintEventArgs e)
        {
            if (image == null || result == null) return;
            // area effettiva dell'immagine dentro il PictureBox (modo Zoom)
            float k = Math.Min(pic.ClientSize.Width / (float)image.Width, pic.ClientSize.Height / (float)image.Height);
            float ox = (pic.ClientSize.Width - image.Width * k) / 2, oy = (pic.ClientSize.Height - image.Height * k) / 2;
            Graphics g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            int sel = list.SelectedIndices.Count > 0 ? list.SelectedIndices[0] : -1;
            float rad = Px(9);
            using (Font f = new Font("Segoe UI", 10f * s, FontStyle.Bold, GraphicsUnit.Pixel))
            using (StringFormat sf = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center })
            {
                for (int i = 0; i < result.Colors.Count; i++)
                {
                    if (sel >= 0 && i != sel) continue; // con un colore selezionato si vedono solo i suoi punti
                    if (i < list.Items.Count && !list.Items[i].Checked && sel < 0) continue;
                    foreach (Point p in result.Colors[i].Points)
                    {
                        float x = ox + p.X * k, y = oy + p.Y * k;
                        RectangleF r = new RectangleF(x - rad, y - rad, 2 * rad, 2 * rad);
                        g.FillEllipse(i == sel ? Brushes.Yellow : Brushes.White, r);
                        g.DrawEllipse(Pens.Black, r);
                        g.DrawString((i + 1).ToString(), f, Brushes.Black, r, sf);
                    }
                }
            }
        }

        // ------------------------------------------------------------------ salvataggio

        private void LoadTargets()
        {
            cmbTarget.Items.Clear();
            foreach (Palette p in PaletteStore.LoadAll(settings.PaletteDir))
                if (!p.IsRecent) cmbTarget.Items.Add(p);
            if (cmbTarget.Items.Count > 0) cmbTarget.SelectedIndex = 0;
        }

        private void UpdateButtons()
        {
            bool has = result != null && result.Colors.Count > 0;
            btnCreate.Enabled = has;
            btnAppend.Enabled = has && cmbTarget.SelectedItem != null;
        }

        /// <summary>Salva i colori spuntati: in una nuova palette (target null) o in fondo a una esistente.</summary>
        private void Save(Palette target)
        {
            if (result == null) return;
            List<VoceColore> voci = new List<VoceColore>();
            for (int i = 0; i < list.Items.Count && i < result.Colors.Count; i++)
                if (list.Items[i].Checked) voci.Add(new VoceColore(names[i], result.Colors[i].Color));
            if (voci.Count == 0)
            {
                MessageBox.Show(this, "Nessun colore spuntato.", "CDV Colori", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }
            try
            {
                if (target == null)
                {
                    string nome = txtName.Text.Trim();
                    if (nome.Length == 0) nome = string.IsNullOrEmpty(imageName) ? "Da immagine" : imageName;
                    target = PaletteStore.Create(settings.PaletteDir, nome);
                }
                else
                {
                    target = Palette.Load(target.FilePath); // versione aggiornata dal disco
                    string gruppo = string.IsNullOrWhiteSpace(txtName.Text) ? "" : txtName.Text.Trim();
                    if (target.HasGroups) foreach (VoceColore v in voci) v.gruppo = gruppo;
                }
                target.Colori.AddRange(voci);
                target.Save();
                MessageBox.Show(this, voci.Count + " colori salvati nella palette \"" + target.Nome + "\".", "CDV Colori",
                    MessageBoxButtons.OK, MessageBoxIcon.Information);
                LoadTargets();
                if (PaletteSaved != null) PaletteSaved(target.Nome);
            }
            catch (Exception ex)
            {
                Log.Write("Salvataggio palette da immagine: " + ex);
                MessageBox.Show(this, "Salvataggio non riuscito:\n" + ex.Message, "CDV Colori", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            }
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                rerun.Dispose();
                if (pic.Image != null) pic.Image.Dispose();
                swatches.Dispose();
            }
            base.Dispose(disposing);
        }
    }
}
