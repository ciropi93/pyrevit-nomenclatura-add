using System;
using System.Threading;
using System.Windows.Forms;

namespace CDVColori
{
    internal static class Program
    {
        [STAThread]
        private static int Main(string[] args)
        {
            Native.EnableDpiAwareness();

            // "CDVColori.exe --diagnosi": scrive solo il rapporto sulla finestra Colore aperta ed esce.
            if (args.Length > 0 && args[0].Trim('-', '/').Equals("diagnosi", StringComparison.OrdinalIgnoreCase))
            {
                string path = Diagnosi.Run(Settings.Load());
                Console.WriteLine(path);
                return 0;
            }

            bool created;
            using (Mutex single = new Mutex(true, @"Local\CDVColori.SingleInstance", out created))
            {
                if (!created)
                {
                    MessageBox.Show("CDV Colori e' gia' in esecuzione (icona nell'area di notifica).", "CDV Colori",
                        MessageBoxButtons.OK, MessageBoxIcon.Information);
                    return 0;
                }
                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                Application.ThreadException += delegate (object s, ThreadExceptionEventArgs e) { Log.Write("Errore: " + e.Exception); };
                AppDomain.CurrentDomain.UnhandledException += delegate (object s, UnhandledExceptionEventArgs e)
                {
                    Log.Write("Errore grave: " + e.ExceptionObject);
                };
                Application.Run(new TrayApp());
            }
            return 0;
        }
    }
}
