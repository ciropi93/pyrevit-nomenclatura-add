using System;
using System.Windows.Forms;

namespace CDVColori
{
    /// <summary>
    /// Osserva Windows "da fuori" (SetWinEventHook out-of-context): si accorge quando un programma
    /// mostra la finestra Colore, quando la sposta e quando la chiude. Non entra nel processo di Revit.
    /// </summary>
    public sealed class DialogWatcher : IDisposable
    {
        public event Action<ColorDialogTarget> Attached;
        public event Action Detached;
        public event Action Moved;

        private readonly Settings settings;
        private readonly Native.WinEventDelegate showProc;
        private readonly Native.WinEventDelegate moveProc;
        private IntPtr showHook = IntPtr.Zero;
        private IntPtr moveHook = IntPtr.Zero;
        private readonly Timer guard;

        public ColorDialogTarget Current { get; private set; }

        public DialogWatcher(Settings settings)
        {
            this.settings = settings;
            showProc = OnShowEvent;
            moveProc = OnMoveEvent;
            guard = new Timer();
            guard.Interval = 400;
            guard.Tick += delegate { if (Current != null && !Current.IsAlive) Detach(); };
        }

        public void Start()
        {
            if (showHook != IntPtr.Zero) return;
            // DESTROY (0x8001), SHOW (0x8002), HIDE (0x8003)
            showHook = Native.SetWinEventHook(Native.EVENT_OBJECT_DESTROY, Native.EVENT_OBJECT_HIDE, IntPtr.Zero,
                showProc, 0, 0, Native.WINEVENT_OUTOFCONTEXT | Native.WINEVENT_SKIPOWNPROCESS);
            if (showHook == IntPtr.Zero) Log.Write("SetWinEventHook non riuscito");
            guard.Start();
            ScanExisting();
        }

        public void Stop()
        {
            guard.Stop();
            Detach();
            if (showHook != IntPtr.Zero) { Native.UnhookWinEvent(showHook); showHook = IntPtr.Zero; }
        }

        /// <summary>Se una finestra Colore e' gia' aperta all'avvio, si aggancia subito.</summary>
        private void ScanExisting()
        {
            IntPtr found = IntPtr.Zero;
            Native.EnumWindows(delegate (IntPtr h, IntPtr l)
            {
                if (Native.IsWindowVisible(h) && ColorDialogTarget.TryCreate(h, settings) != null)
                {
                    found = h;
                    return false;
                }
                return true;
            }, IntPtr.Zero);
            if (found != IntPtr.Zero) TryAttach(found);
        }

        private void OnShowEvent(IntPtr hook, uint ev, IntPtr hwnd, int idObject, int idChild, uint thread, uint time)
        {
            if (idObject != Native.OBJID_WINDOW || idChild != Native.CHILDID_SELF || hwnd == IntPtr.Zero) return;
            try
            {
                if (ev == Native.EVENT_OBJECT_SHOW)
                {
                    if (Current != null && Current.Hwnd == hwnd) return;
                    TryAttach(hwnd);
                }
                else if (Current != null && Current.Hwnd == hwnd)
                {
                    Detach();
                }
            }
            catch (Exception ex) { Log.Write("Evento finestra: " + ex); }
        }

        private void TryAttach(IntPtr hwnd)
        {
            ColorDialogTarget t = ColorDialogTarget.TryCreate(hwnd, settings);
            if (t == null) return;
            if (Current != null) Detach();
            Current = t;
            Log.Write("Finestra Colore agganciata (" + t.ProcessName + ", " + hwnd + ")");
            moveHook = Native.SetWinEventHook(Native.EVENT_OBJECT_LOCATIONCHANGE, Native.EVENT_OBJECT_LOCATIONCHANGE,
                IntPtr.Zero, moveProc, t.ProcessId, t.ThreadId, Native.WINEVENT_OUTOFCONTEXT);
            if (Attached != null) Attached(t);
        }

        private void OnMoveEvent(IntPtr hook, uint ev, IntPtr hwnd, int idObject, int idChild, uint thread, uint time)
        {
            if (Current == null || hwnd != Current.Hwnd || idObject != Native.OBJID_WINDOW) return;
            try { if (Moved != null) Moved(); }
            catch (Exception ex) { Log.Write("Spostamento: " + ex); }
        }

        public void Detach()
        {
            if (moveHook != IntPtr.Zero) { Native.UnhookWinEvent(moveHook); moveHook = IntPtr.Zero; }
            if (Current == null) return;
            Current = null;
            try { if (Detached != null) Detached(); }
            catch (Exception ex) { Log.Write("Sgancio: " + ex); }
        }

        public void Dispose()
        {
            Stop();
            guard.Dispose();
        }
    }
}
