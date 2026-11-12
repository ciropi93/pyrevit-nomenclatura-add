using System;
using System.Collections.Generic;
using System.Drawing;

namespace CDVColori
{
    /// <summary>Opzioni di estrazione dei colori da un'immagine.</summary>
    public sealed class ExtractOptions
    {
        /// <summary>Numero massimo di colori restituiti (i piu' estesi).</summary>
        public int MaxColors = 60;
        /// <summary>Colori con distanza percettiva (Delta E) inferiore vengono fusi in uno.</summary>
        public double MergeDeltaE = 3.0;
        public bool IgnoreWhite = true;
        public bool IgnoreBlack = false;
        public bool SortByHue = false;
        /// <summary>L'immagine viene ridotta a questo lato massimo prima dell'analisi.</summary>
        public int MaxSide = 900;
        /// <summary>Colori per la quantizzazione di ripiego (foto, sfumature).</summary>
        public int FallbackColors = 12;
    }

    /// <summary>Un colore trovato: valore, area (pixel dell'immagine originale) e punti dove compare.</summary>
    public sealed class FoundColor
    {
        public Color Color;
        public long Area;
        public double AreaPercent;
        public List<Point> Points = new List<Point>();
    }

    /// <summary>Esito dell'estrazione.</summary>
    public sealed class ExtractResult
    {
        public List<FoundColor> Colors = new List<FoundColor>();
        /// <summary>True se l'immagine non aveva zone piatte e si e' usata la quantizzazione (es. foto).</summary>
        public bool UsedFallback;
    }

    /// <summary>
    /// Estrae i colori "piatti" di un'immagine (grafici, schemi, legende, palette).
    /// 1) riduzione a MaxSide; 2) pixel con bassa variazione locale (5x5): esclude testo e bordi sfumati;
    /// 3) zone collegate di colore uniforme; 4) colore mediano di ogni zona; 5) fusione dei colori quasi uguali (Lab).
    /// Se le zone piatte sono poche (foto) si ripiega su una quantizzazione median-cut.
    /// Nessuna dipendenza da interfaccia: lavora su un array di pixel ARGB (compilato anche dai test).
    /// </summary>
    public static class ImagePalette
    {
        private const double FlatStd = 9.0;      // somma delle deviazioni standard R+G+B nel 5x5
        private const int NeighborDiff = 12;     // |dR|+|dG|+|dB| tra pixel vicini della stessa zona
        private const double MinRegionFrac = 0.0004;
        private const int MinRegionPx = 25;

        public static ExtractResult Extract(int[] argb, int width, int height, ExtractOptions o)
        {
            if (o == null) o = new ExtractOptions();
            if (argb == null || width <= 0 || height <= 0 || argb.Length < width * height)
                throw new ArgumentException("Immagine non valida");

            // 1) riduzione (media a blocchi)
            int f = Math.Max(1, (int)Math.Ceiling(Math.Max(width, height) / (double)o.MaxSide));
            int w = width / f, h = height / f;
            if (w < 1 || h < 1) { f = 1; w = width; h = height; }
            int n = w * h;
            byte[] R = new byte[n], G = new byte[n], B = new byte[n];
            for (int y = 0; y < h; y++)
                for (int x = 0; x < w; x++)
                {
                    int sr = 0, sg = 0, sb = 0;
                    for (int dy = 0; dy < f; dy++)
                    {
                        int row = (y * f + dy) * width + x * f;
                        for (int dx = 0; dx < f; dx++)
                        {
                            int p = argb[row + dx];
                            sr += (p >> 16) & 0xFF; sg += (p >> 8) & 0xFF; sb += p & 0xFF;
                        }
                    }
                    int k = f * f, i = y * w + x;
                    R[i] = (byte)(sr / k); G[i] = (byte)(sg / k); B[i] = (byte)(sb / k);
                }

            // 2) pixel piatti
            bool[] flat = FlatMask(R, G, B, w, h);
            bool[] ignored = new bool[n];
            int considered = 0;
            for (int i = 0; i < n; i++)
            {
                int mn = Math.Min(R[i], Math.Min(G[i], B[i])), mx = Math.Max(R[i], Math.Max(G[i], B[i]));
                ignored[i] = (o.IgnoreWhite && mn > 245) || (o.IgnoreBlack && mx < 12);
                if (!ignored[i]) considered++;
            }

            // 3-4) zone collegate
            int minRegion = Math.Max(MinRegionPx, (int)(n * MinRegionFrac));
            int[] label = new int[n];
            int[] stack = new int[n];
            List<Region> regions = new List<Region>();
            long flatCovered = 0;
            int next = 0;
            for (int start = 0; start < n; start++)
            {
                if (label[start] != 0 || !flat[start] || ignored[start]) continue;
                next++;
                List<int> members = new List<int>();
                int sp = 0;
                stack[sp++] = start;
                label[start] = next;
                while (sp > 0)
                {
                    int i = stack[--sp];
                    members.Add(i);
                    int x = i % w, y = i / w;
                    if (x + 1 < w) Visit(i, i + 1, R, G, B, flat, ignored, label, next, stack, ref sp);
                    if (x > 0) Visit(i, i - 1, R, G, B, flat, ignored, label, next, stack, ref sp);
                    if (y + 1 < h) Visit(i, i + w, R, G, B, flat, ignored, label, next, stack, ref sp);
                    if (y > 0) Visit(i, i - w, R, G, B, flat, ignored, label, next, stack, ref sp);
                }
                if (members.Count < minRegion) continue;
                flatCovered += members.Count;
                regions.Add(MakeRegion(members, R, G, B, w, f));
            }

            ExtractResult res = new ExtractResult();
            if (regions.Count < 2 || flatCovered < considered * 0.15)
            {
                res.UsedFallback = true;
                regions = MedianCut(R, G, B, ignored, w, f, Math.Max(2, Math.Min(o.FallbackColors, o.MaxColors)));
            }

            // 5) fusione dei colori quasi uguali (le zone piu' grandi comandano)
            regions.Sort((a, b) => b.Count.CompareTo(a.Count));
            double total = 0;
            foreach (Region r in regions) total += r.Count;
            List<FoundColor> found = new List<FoundColor>();
            foreach (Region r in regions)
            {
                FoundColor target = null;
                double best = double.MaxValue;
                foreach (FoundColor fc in found)
                {
                    double d = ColorText.DeltaE(fc.Color, r.Color);
                    if (d < o.MergeDeltaE && d < best) { best = d; target = fc; }
                }
                if (target == null)
                {
                    target = new FoundColor();
                    target.Color = r.Color;
                    found.Add(target);
                }
                target.Area += (long)r.Count * f * f;
                target.AreaPercent += total > 0 ? 100.0 * r.Count / total : 0;
                if (r.HasPoint) target.Points.Add(r.Point);
            }

            found.Sort((a, b) => b.Area.CompareTo(a.Area));
            if (found.Count > o.MaxColors) found.RemoveRange(o.MaxColors, found.Count - o.MaxColors);
            if (o.SortByHue) found.Sort(CompareHue);
            res.Colors = found;
            return res;
        }

        private sealed class Region
        {
            public Color Color;
            public int Count;
            public Point Point;
            public bool HasPoint;
        }

        private static void Visit(int from, int to, byte[] R, byte[] G, byte[] B, bool[] flat, bool[] ignored,
            int[] label, int id, int[] stack, ref int sp)
        {
            if (label[to] != 0 || !flat[to] || ignored[to]) return;
            int d = Math.Abs(R[from] - R[to]) + Math.Abs(G[from] - G[to]) + Math.Abs(B[from] - B[to]);
            if (d >= NeighborDiff) return;
            label[to] = id;
            stack[sp++] = to;
        }

        /// <summary>Pixel con variazione locale bassa (immagini integrali su finestra 5x5).</summary>
        private static bool[] FlatMask(byte[] R, byte[] G, byte[] B, int w, int h)
        {
            double[] std = new double[w * h];
            foreach (byte[] ch in new[] { R, G, B })
            {
                long[] s1 = new long[(w + 1) * (h + 1)];
                long[] s2 = new long[(w + 1) * (h + 1)];
                for (int y = 0; y < h; y++)
                {
                    long r1 = 0, r2 = 0;
                    for (int x = 0; x < w; x++)
                    {
                        int v = ch[y * w + x];
                        r1 += v; r2 += v * v;
                        int k = (y + 1) * (w + 1) + (x + 1);
                        s1[k] = s1[k - (w + 1)] + r1;
                        s2[k] = s2[k - (w + 1)] + r2;
                    }
                }
                for (int y = 0; y < h; y++)
                {
                    int y0 = Math.Max(0, y - 2), y1 = Math.Min(h, y + 3);
                    for (int x = 0; x < w; x++)
                    {
                        int x0 = Math.Max(0, x - 2), x1 = Math.Min(w, x + 3);
                        int cnt = (y1 - y0) * (x1 - x0);
                        long a = s1[y1 * (w + 1) + x1] - s1[y0 * (w + 1) + x1] - s1[y1 * (w + 1) + x0] + s1[y0 * (w + 1) + x0];
                        long b = s2[y1 * (w + 1) + x1] - s2[y0 * (w + 1) + x1] - s2[y1 * (w + 1) + x0] + s2[y0 * (w + 1) + x0];
                        double mean = a / (double)cnt;
                        double var = b / (double)cnt - mean * mean;
                        std[y * w + x] += Math.Sqrt(Math.Max(0, var));
                    }
                }
            }
            bool[] flat = new bool[w * h];
            for (int i = 0; i < flat.Length; i++) flat[i] = std[i] < FlatStd;
            return flat;
        }

        /// <summary>Colore mediano della zona e suo punto piu' vicino al baricentro (per il segnaposto).</summary>
        private static Region MakeRegion(List<int> members, byte[] R, byte[] G, byte[] B, int w, int f)
        {
            int[] hr = new int[256], hg = new int[256], hb = new int[256];
            double cx = 0, cy = 0;
            foreach (int i in members)
            {
                hr[R[i]]++; hg[G[i]]++; hb[B[i]]++;
                cx += i % w; cy += i / w;
            }
            cx /= members.Count; cy /= members.Count;
            int best = members[0];
            double bd = double.MaxValue;
            foreach (int i in members)
            {
                double dx = i % w - cx, dy = i / w - cy, d = dx * dx + dy * dy;
                if (d < bd) { bd = d; best = i; }
            }
            Region r = new Region();
            r.Count = members.Count;
            r.Color = Color.FromArgb(Median(hr, members.Count), Median(hg, members.Count), Median(hb, members.Count));
            r.Point = new Point((best % w) * f + f / 2, (best / w) * f + f / 2);
            r.HasPoint = true;
            return r;
        }

        private static int Median(int[] hist, int count)
        {
            int half = (count + 1) / 2, acc = 0;
            for (int v = 0; v < 256; v++)
            {
                acc += hist[v];
                if (acc >= half) return v;
            }
            return 255;
        }

        /// <summary>Quantizzazione median-cut: per immagini senza zone piatte (foto, sfumature).</summary>
        private static List<Region> MedianCut(byte[] R, byte[] G, byte[] B, bool[] ignored, int w, int f, int k)
        {
            List<int> all = new List<int>();
            int step = Math.Max(1, R.Length / 200000); // basta un campione
            for (int i = 0; i < R.Length; i += step) if (!ignored[i]) all.Add(i);
            List<List<int>> boxes = new List<List<int>>();
            if (all.Count > 0) boxes.Add(all);
            while (boxes.Count < k)
            {
                int bi = -1, bestRange = 0, bestCh = 0;
                for (int j = 0; j < boxes.Count; j++)
                {
                    if (boxes[j].Count < 2) continue;
                    int ch, range;
                    WidestChannel(boxes[j], R, G, B, out ch, out range);
                    if (range > bestRange) { bestRange = range; bi = j; bestCh = ch; }
                }
                if (bi < 0 || bestRange == 0) break;
                List<int> box = boxes[bi];
                byte[] c = bestCh == 0 ? R : bestCh == 1 ? G : B;
                box.Sort((a, b) => c[a].CompareTo(c[b]));
                int mid = box.Count / 2;
                boxes[bi] = box.GetRange(0, mid);
                boxes.Add(box.GetRange(mid, box.Count - mid));
            }
            List<Region> res = new List<Region>();
            foreach (List<int> box in boxes)
            {
                Region r = MakeRegion(box, R, G, B, w, f);
                r.Count = box.Count * step;
                r.HasPoint = false; // in una foto il "punto" del colore non e' significativo
                res.Add(r);
            }
            return res;
        }

        private static void WidestChannel(List<int> box, byte[] R, byte[] G, byte[] B, out int ch, out int range)
        {
            int[] mn = { 255, 255, 255 }, mx = { 0, 0, 0 };
            foreach (int i in box)
            {
                if (R[i] < mn[0]) mn[0] = R[i]; if (R[i] > mx[0]) mx[0] = R[i];
                if (G[i] < mn[1]) mn[1] = G[i]; if (G[i] > mx[1]) mx[1] = G[i];
                if (B[i] < mn[2]) mn[2] = B[i]; if (B[i] > mx[2]) mx[2] = B[i];
            }
            ch = 0; range = mx[0] - mn[0];
            if (mx[1] - mn[1] > range) { ch = 1; range = mx[1] - mn[1]; }
            if (mx[2] - mn[2] > range) { ch = 2; range = mx[2] - mn[2]; }
        }

        /// <summary>Ordine per tinta: prima i grigi (dal chiaro allo scuro), poi i colori per tinta e luminosita'.</summary>
        private static int CompareHue(FoundColor a, FoundColor b)
        {
            double ha, sa, la, hb, sb, lb;
            ColorText.ToHsl(a.Color, out ha, out sa, out la);
            ColorText.ToHsl(b.Color, out hb, out sb, out lb);
            bool ga = sa < 0.08, gb = sb < 0.08;
            if (ga != gb) return ga ? -1 : 1;
            if (ga) return lb.CompareTo(la);
            int c = Math.Round(ha * 24).CompareTo(Math.Round(hb * 24));
            return c != 0 ? c : lb.CompareTo(la);
        }
    }
}
