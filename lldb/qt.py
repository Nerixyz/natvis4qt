import lldb
from lldb import SBValue, SBType, SBTarget, SBData, SBError, SBDebugger


def __lldb_init_module(dbg: SBDebugger, internal_dict):
    dbg.HandleCommand("type category define -e qt -l c++")

    def add_summary(type_name: str, *, regex: str | None = None):
        cmd = f"type summary add -w qt -F {__name__}.{type_name}SummaryProvider"
        if regex:
            cmd += f' -x "{regex}"'
        else:
            cmd += f' "{type_name}"'
        dbg.HandleCommand(cmd)

    def add_synthetic(name: str, *, regex: str | None = None):
        cmd = f"type synthetic add -w qt -l {__name__}.{name}SyntheticProvider"
        if regex:
            cmd += f' -x "{regex}"'
        else:
            cmd += f' "{name}"'
        dbg.HandleCommand(cmd)

    add_summary("QString")
    add_summary("QUuid")
    add_summary("QRect")
    add_synthetic("QCheckedInt", regex="^QtPrivate::QCheckedIntegers::QCheckedInt<.*>$")
    # _add_summary_string(
    #     dbg, "^QtPrivate::QCheckedIntegers::QCheckedInt<.*>$", "${var.m_i}", regex=True
    # )
    _add_summary_string(dbg, "QPoint", "(x: ${var.xp}, y: ${var.yp})")
    _add_summary_string(
        dbg,
        "QRectF",
        "(x: ${var.xp}, y: ${var.yp}, width: ${var.w}, height: ${var.h})",
    )


def _add_summary_string(dbg: SBDebugger, type_name: str, summary: str, *, regex=False):
    cmd = f"type summary add -w qt --summary-string '{summary}' {'-x' if regex else ''} \"{type_name}\""
    dbg.HandleCommand(cmd)


def QStringSummaryProvider(
    valobj: SBValue, internal_dict: dict, options: lldb.SBTypeSummaryOptions
) -> str | None:
    d_obj: SBValue = valobj.GetChildMemberWithName("d")
    ptr_obj: SBValue = d_obj.GetChildMemberWithName("ptr")
    size = d_obj.GetChildMemberWithName("size").unsigned
    if not ptr_obj.IsValid():
        return None
    if ptr_obj.GetValueAsUnsigned() == 0:
        return 'u"" (null)'
    if size == 0:
        return 'u""'
    array_type = valobj.target.GetBasicType(lldb.eBasicTypeChar16).GetArrayType(size)
    return ptr_obj.deref.Cast(array_type).summary


def QUuidSummaryProvider(
    valobj: SBValue, internal_dict: dict, options: lldb.SBTypeSummaryOptions
) -> str | None:
    data1 = valobj.GetChildMemberWithName("data1").unsigned
    data2 = valobj.GetChildMemberWithName("data2").unsigned
    data3 = valobj.GetChildMemberWithName("data3").unsigned
    data4 = valobj.GetChildMemberWithName("data4").GetData()
    e = SBError()
    data4 = data4.ReadRawData(e, 0, 8)
    if e.Fail():
        return None
    return f"{data1:08x}-{data2:04x}-{data3:04x}-{data4[0]:02x}{data4[1]:02x}-{data4[2]:02x}{data4[3]:02x}{data4[4]:02x}{data4[5]:02x}{data4[6]:02x}{data4[7]:02x}"


def QRectSummaryProvider(
    valobj: SBValue, internal_dict: dict, options: lldb.SBTypeSummaryOptions
) -> str | None:
    x1 = valobj.GetChildMemberWithName("x1").signed
    x2 = valobj.GetChildMemberWithName("x2").signed
    y1 = valobj.GetChildMemberWithName("y1").signed
    y2 = valobj.GetChildMemberWithName("y2").signed
    return f"(x: {x1}, y: {y1}, width: {x2 - x1 + 1}, height: {y2 - y1 + 1})"


class QCheckedIntSyntheticProvider(lldb.SBSyntheticValueProvider):
    def __init__(self, valobj: SBValue, internal_dict):
        self._backend = valobj

    def update(self):
        self._val = self._backend.GetChildAtIndex(0)

    def get_value(self):
        return self._val
