import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.mem.*;
import ghidra.app.cmd.disassemble.DisassembleCommand;
import java.io.*;
import java.nio.file.*;
import java.nio.*;
import java.util.*;

public class NaviDecomp extends GhidraScript {
    public void run() throws Exception {
        String[] a = getScriptArgs();
        String dataFile = a[0], pdataFile = a[1], outFile = a[2];
        Memory mem = currentProgram.getMemory();
        AddressSpace sp = currentProgram.getAddressFactory().getDefaultAddressSpace();
        if (mem.getBlock(sp.getAddress(0x55d000L)) == null) {
            byte[] d = Files.readAllBytes(Paths.get(dataFile));
            MemoryBlock b = mem.createInitializedBlock("data", sp.getAddress(0x55d000L), d.length, (byte)0, monitor, false);
            mem.setBytes(sp.getAddress(0x55d000L), d);
            b.setRead(true); b.setWrite(true); b.setExecute(false);
        }
        byte[] p = Files.readAllBytes(Paths.get(pdataFile));
        ByteBuffer bb = ByteBuffer.wrap(p).order(ByteOrder.LITTLE_ENDIAN);
        int made = 0;
        for (int i = 0; i + 8 <= p.length; i += 8) {
            long beg = bb.getInt(i) & 0xffffffffL;
            if (beg < 0x11000L || beg >= 0x55d000L) continue;
            Address ad = sp.getAddress(beg);
            if (getFunctionAt(ad) == null) {
                new DisassembleCommand(ad, null, true).applyTo(currentProgram, monitor);
                if (createFunction(ad, null) != null) made++;
            }
        }
        println("functions created: " + made);
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        PrintWriter out = new PrintWriter(new FileWriter(outFile));
        if (a.length > 3 && a[3].equals("ALL")) {
            int n = 0;
            for (Function f : currentProgram.getFunctionManager().getFunctions(true)) {
                DecompileResults r = di.decompileFunction(f, 60, monitor);
                out.println("// ===== " + f.getEntryPoint() + " " + f.getName());
                out.println(r.decompileCompleted() ? r.getDecompiledFunction().getC() : ("// FAILED " + r.getErrorMessage()));
                if (++n % 500 == 0) println("decompiled " + n);
            }
            out.close();
            return;
        }
        for (int k = 3; k < a.length; k++) {
            long va = Long.decode(a[k]);
            Function f = getFunctionContaining(sp.getAddress(va));
            if (f == null) {
                new DisassembleCommand(sp.getAddress(va), null, true).applyTo(currentProgram, monitor);
                f = createFunction(sp.getAddress(va), null);
            }
            if (f == null) { out.println("// no function at " + a[k]); continue; }
            DecompileResults r = di.decompileFunction(f, 120, monitor);
            out.println("// ===== " + a[k] + " in " + f.getName() + " @ " + f.getEntryPoint());
            out.println(r.decompileCompleted() ? r.getDecompiledFunction().getC() : ("// FAILED " + r.getErrorMessage()));
        }
        out.close();
    }
}
