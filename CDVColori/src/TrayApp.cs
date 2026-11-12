using System;
using System.Diagnostics;
using System.Drawing;
using System.Windows.Forms;
using Microsoft.Win32;

namespace CDVColori
{
    /// <summary>Programma nell'area di notifica: collega osservatore, contagocce e pannello palette.</summary>
    internal sealed class TrayApp : ApplicationContext
    {
        private const string RunKey = @"Software\Microsoft\Windows\CurrentVersion\Run";
        private const string RunName = "CDVColori";

        private readonly Settings settings;
        private readonly DialogWatcher watcher;
        private readonly NotifyIcon tray = new NotifyIcon();
        private readonly ToolStripMenuItem miActive, miPanel, miDropper, miStartup;
        private readonly Icon iconOn, iconOff;

        private EyedropperButton dropper;
        private PalettePanel panel;

        public TrayApp()
        {
            settings = Settings.Load();
            iconOn = Icons.TrayIcon(32, true);
            iconOff = Icons.TrayIcon(32, false);

            ContextMenuStrip menu = new ContextMenuStrip();
            miActive = new ToolStripMenuItem("Attivo", null, delegate { SetActive(!settings.attivo); });
            miPanel = new ToolStripMenuItem("Mostra pannello palette", null, delegate
            {
                settings.mostraPannello = !settings.mostraPannello; settings.Save(); RefreshMenu(); Reattach();
            });
            miDropper = new ToolStripMenuItem("Mostra contagocce", null, delegate
            {
                settings.mostraContagocce = !settings.mostraContagocce; settings.Save(); RefreshMenu(); Reattach();
            });
            miStartup = new ToolStripMenuItem("Avvia con Windows", null, delegate { ToggleStartup(); });
            menu.Items.Add(miActive);
            menu.Items.Add(miPanel);
            menu.Items.Add(miDropper);
            menu.Items.Add(new ToolStripSeparator());
            menu.Items.Add("Contagocce (senza finestra Colore)", null, delegate { PickToClipboard(); });
            menu.Items.Add("Apri cartella palette", null, delegate { PalettePanel.OpenFolder(settings.PaletteDir); });
            menu.Items.Add("Apri impostazioni (config.json)", null, delegate { OpenFile(Settings.FilePath); });
            menu.Items.Add("Estrai palette da immagine\u2026", null, delegate { OpenExtractor(); });
            menu.Items.Add("Diagnosi finestra Colore", null, delegate { RunDiagnosi(); });
            menu.Items.Add(new ToolStripSeparator());
            menu.Items.Add(miStartup);
            menu.Items.Add("Esci", null, delegate { ExitThread(); });

            tray.ContextMenuStrip = menu;
            tray.Text = "CDV Colori";
            tray.Visible = true;
            tray.DoubleClick += delegate { SetActive(!settings.attivo); };

            watcher = new DialogWatcher(settings);
            watcher.Attached += OnAttached;
            watcher.Detached += OnDetached;
            watcher.Moved += OnMoved;

            RefreshMenu();
            if (settings.attivo) watcher.Start();
            tray.ShowBalloonTip(3000, "CDV Colori",
                settings.attivo ? "Attivo: apri la finestra Colore in Revit." : "In pausa (doppio clic sull'icona per attivare).",
                ToolTipIcon.Info);
            Log.Write("Avvio. Programmi: " + string.Join(", ", settings.programmi.ToArray()));
        }

        private void RefreshMenu()
        {
            miActive.Checked = settings.attivo;
            miPanel.Checked = settings.mostraPannello;
            miDropper.Checked = settings.mostraContagocce;
            miStartup.Checked = IsStartupEnabled();
            tray.Icon = settings.attivo ? iconOn : iconOff;
            tray.Text = settings.attivo ? "CDV Colori (attivo)" : "CDV Colori (in pausa)";
        }

        private void SetActive(bool on)
        {
            settings.attivo = on;
            settings.Save();
            if (on) watcher.Start(); else watcher.Stop();
            RefreshMenu();
        }

        private void Reattach()
        {
            if (!settings.attivo) return;
            watcher.Stop();
            watcher.Start();
        }

        // ---------- aggancio alla finestra Colore ----------

        private void OnAttached(ColorDialogTarget t)
        {
            float scale = t.Scale;

            if (settings.mostraContagocce)
            {
                if (dropper == null || dropper.IsDisposed)
                {
                    dropper = new EyedropperButton();
                    dropper.Clicked += StartPick;
                }
                dropper.Picking = false;
                SetOwner(dropper, t);
                dropper.PlaceOn(t);
                if (!dropper.Visible) dropper.Show();
            }

            if (settings.mostraPannello)
            {
                if (panel != null && (panel.IsDisposed || Math.Abs(panel.ScaleFactor - scale) > 0.01f))
                {
                    if (!panel.IsDisposed) panel.Dispose();
                    panel = null;
                }
                if (panel == null)
                {
                    panel = new PalettePanel(settings, scale);
                    panel.ApplyColor = ApplyToDialog;
                    panel.ExtractRequested += OpenExtractor;
                    panel.ReadCurrent = delegate
                    {
                        ColorDialogTarget cur = watcher.Current;
                        return cur != null ? cur.ReadRgb() : null;
                    };
                }
                else
                {
                    panel.Reload();
                }
                SetOwner(panel, t);
                panel.PlaceBeside(t);
                if (!panel.Visible) panel.Show();
            }
        }

        /// <summary>Rende la nostra finestra "di proprieta'" della finestra Colore: le resta sopra e la segue.</summary>
        private static void SetOwner(Form f, ColorDialogTarget t)
        {
            IntPtr h = f.Handle; // crea la finestra se serve
            Native.SetOwner(h, t.Hwnd);
        }

        private void OnMoved()
        {
            ColorDialogTarget t = watcher.Current;
            if (t == null) return;
            if (dropper != null && dropper.Visible) dropper.PlaceOn(t);
            if (panel != null && panel.Visible) panel.PlaceBeside(t);
        }

        private void OnDetached()
        {
            if (PickSession.Active != null) return; // la scelta in corso finisce da sola
            HideOwned(dropper);
            HideOwned(panel);
        }

        private static void HideOwned(Form f)
        {
            if (f == null || f.IsDisposed) return;
            f.Hide();
            Native.SetOwner(f.Handle, IntPtr.Zero);
        }

        private bool ApplyToDialog(Color c, bool pressOk)
        {
            ColorDialogTarget t = watcher.Current;
            if (t == null || !t.IsAlive) return false;
            bool ok = t.SetRgb(c);
            if (ok && pressOk) t.PressOk();
            return ok;
        }

        // ---------- contagocce ----------

        private void StartPick()
        {
            if (dropper != null) dropper.Picking = true;
            PickSession.Start(settings, delegate (Color c)
            {
                ColorDialogTarget t = watcher.Current;
                if (t != null && t.IsAlive)
                {
                    if (!t.SetRgb(c))
                        tray.ShowBalloonTip(3000, "CDV Colori", "Colore preso (" + ColorText.ToHex(c) +
                            ") ma non riesco a scriverlo nella finestra Colore.", ToolTipIcon.Warning);
                }
                if (panel != null && !panel.IsDisposed) panel.NotifyPicked(c);
            }, CollectRecent, delegate
            {
                if (dropper != null && !dropper.IsDisposed) dropper.Picking = false;
                ColorDialogTarget t = watcher.Current;
                if (t == null || !t.IsAlive) OnDetached();
            });
        }

        /// <summary>Contagocce dal menu: copia il colore negli appunti (#RRGGBB) e lo aggiunge ai recenti.</summary>
        private void PickToClipboard()
        {
            PickSession.Start(settings, delegate (Color c)
            {
                string hex = ColorText.ToHex(c);
                try { Clipboard.SetText(hex); } catch { }
                PaletteStore.AddRecent(PaletteStore.LoadRecenti(), c);
                tray.ShowBalloonTip(2500, "CDV Colori", hex + "  (RGB " + ColorText.ToRgb(c) + ") copiato negli appunti",
                    ToolTipIcon.Info);
            }, CollectRecent, null);
        }

        /// <summary>Maiusc+clic col contagocce: il colore va nei Recenti e si continua.</summary>
        private void CollectRecent(Color c)
        {
            if (panel != null && !panel.IsDisposed && panel.Visible) panel.NotifyPicked(c);
            else PaletteStore.AddRecent(PaletteStore.LoadRecenti(), c);
        }

        // ---------- estrazione da immagine ----------

        private ImagePaletteForm extractor;

        private void OpenExtractor()
        {
            if (extractor != null && !extractor.IsDisposed)
            {
                if (extractor.WindowState == FormWindowState.Minimized) extractor.WindowState = FormWindowState.Normal;
                extractor.Activate();
                return;
            }
            extractor = new ImagePaletteForm(settings);
            extractor.PaletteSaved += delegate (string nome)
            {
                if (panel != null && !panel.IsDisposed) panel.SelectPalette(nome);
            };
            extractor.FormClosed += delegate { extractor = null; };
            extractor.Show();
            extractor.Activate();
        }

        // ---------- varie ----------

        private void RunDiagnosi()
        {
            try
            {
                string path = Diagnosi.Run(settings);
                OpenFile(path);
            }
            catch (Exception ex)
            {
                Log.Write("Diagnosi: " + ex);
                MessageBox.Show("Diagnosi non riuscita: " + ex.Message, "CDV Colori");
            }
        }

        private static void OpenFile(string path)
        {
            try { Process.Start("notepad.exe", "\"" + path + "\""); } catch (Exception ex) { Log.Write(ex.Message); }
        }

        private static bool IsStartupEnabled()
        {
            try
            {
                using (RegistryKey k = Registry.CurrentUser.OpenSubKey(RunKey))
                    return k != null && k.GetValue(RunName) != null;
            }
            catch { return false; }
        }

        private void ToggleStartup()
        {
            try
            {
                using (RegistryKey k = Registry.CurrentUser.CreateSubKey(RunKey))
                {
                    if (IsStartupEnabled()) k.DeleteValue(RunName, false);
                    else k.SetValue(RunName, "\"" + Application.ExecutablePath + "\"");
                }
            }
            catch (Exception ex) { Log.Write("Avvio automatico: " + ex.Message); }
            RefreshMenu();
        }

        protected override void ExitThreadCore()
        {
            watcher.Dispose();
            if (dropper != null) dropper.Dispose();
            if (panel != null) panel.Dispose();
            if (extractor != null && !extractor.IsDisposed) extractor.Dispose();
            tray.Visible = false;
            tray.Dispose();
            iconOn.Dispose();
            iconOff.Dispose();
            Log.Write("Uscita");
            base.ExitThreadCore();
        }
    }
}
