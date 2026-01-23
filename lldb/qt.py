import lldb
from lldb import SBValue, SBType, SBTarget, SBData, SBError, SBDebugger
from typing import Callable


def __lldb_init_module(dbg: SBDebugger, internal_dict):
    dbg.HandleCommand("type category define -e qt -l c++")

    def add_summary(type_name: str, *, regex: str | None = None):
        cmd = f"type summary add -w qt -F {__name__}.{type_name}SummaryProvider"
        if regex:
            cmd += f' -x "{regex}"'
        else:
            cmd += f' "{type_name}"'
        dbg.HandleCommand(cmd)

    def add_synthetic(
        name: str, *, regex: str | None = None, other_names: list[str] = []
    ):
        cmd = f"type synthetic add -w qt -l {__name__}.{name}SyntheticProvider"
        if regex:
            cmd += f' -x "{regex}"'
        else:
            cmd += f' "{name}" ' + " ".join(map(lambda it: f'"{it}"', other_names))
        dbg.HandleCommand(cmd)

    add_summary("QString")
    add_summary("QUuid")
    add_summary("QRect")
    add_synthetic("QCheckedInt", regex="^QtPrivate::QCheckedIntegers::QCheckedInt<.*>$")
    add_synthetic("QSize", other_names=["QSizeF"])
    add_synthetic("QRect")
    _add_summary_string(dbg, ["QPoint", "QPointF"], "(x: ${var.xp}, y: ${var.yp})")
    _add_summary_string(
        dbg, ["QSize", "QSizeF"], "(width: ${var.wd}, height: ${var.ht})"
    )
    _add_summary_string(
        dbg,
        "QRectF",
        "(x: ${var.xp}, y: ${var.yp}, width: ${var.w}, height: ${var.h})",
    )


def _add_summary_string(
    dbg: SBDebugger, type_names: str | list[str], summary: str, *, regex=False
):
    if isinstance(type_names, str):
        type_names = [type_names]
    cmd = (
        f"type summary add -w qt --summary-string '{summary}' {'-x' if regex else ''} "
    )
    cmd += " ".join(map(lambda it: f'"{it}"', type_names))
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
    valobj = valobj.GetNonSyntheticValue()
    x1 = valobj.GetChildMemberWithName("x1").GetSyntheticValue().signed
    x2 = valobj.GetChildMemberWithName("x2").GetSyntheticValue().signed
    y1 = valobj.GetChildMemberWithName("y1").GetSyntheticValue().signed
    y2 = valobj.GetChildMemberWithName("y2").GetSyntheticValue().signed
    return f"(x: {x1}, y: {y1}, width: {x2 - x1 + 1}, height: {y2 - y1 + 1})"


class QCheckedIntSyntheticProvider(lldb.SBSyntheticValueProvider):
    def __init__(self, valobj: SBValue, internal_dict):
        self._backend = valobj

    def update(self):
        self._val = self._backend.GetChildAtIndex(0)

    def get_value(self):
        return self._val


class _DispatchedSynthetic:
    items: list[tuple[str, Callable | str]] = []
    cache: dict[int, SBValue] = {}

    def __init__(self, valobj: SBValue, internal_dict):
        self._valobj = valobj

    def num_children(self):
        return len(self.items)

    def get_child_index(self, name: str):
        name = name.removeprefix("[").removesuffix("]")
        for i, (k, v) in enumerate(self.items):
            if name == k:
                return i
        return None

    def get_child_at_index(self, idx: int):
        if idx < 0 or idx >= len(self.items):
            return None
        existing = self.cache.get(idx)
        if existing is not None:
            return existing
        v = self._get_at_index(idx)
        self.cache[idx] = v
        return v

    def _get_at_index(self, idx: int):
        key, item = self.items[idx]
        if isinstance(item, str):
            return self._valobj.GetChildMemberWithName(item).Clone(f"[{key}]")
        # else: callable
        return item(self, self._valobj).Clone(f"[{key}]")

    def update(self):
        self.cache.clear()
        return False

    def has_children(self):
        return len(self.items) > 0


class QSizeSyntheticProvider(_DispatchedSynthetic):
    items = [
        ("width", "wd"),
        ("height", "ht"),
    ]


class QRectSyntheticProvider(_DispatchedSynthetic):
    def _get_width(self, valobj: SBValue):
        x1 = valobj.GetChildMemberWithName("x1").GetSyntheticValue().signed
        x2 = valobj.GetChildMemberWithName("x2").GetSyntheticValue().signed
        return _valobj_from_signed(valobj, x2 - x1 + 1)

    def _get_height(self, valobj: SBValue):
        y1 = valobj.GetChildMemberWithName("y1").GetSyntheticValue().signed
        y2 = valobj.GetChildMemberWithName("y2").GetSyntheticValue().signed
        return _valobj_from_signed(valobj, y2 - y1 + 1)

    items = [
        ("x", "x1"),
        ("y", "y1"),
        ("width", _get_width),
        ("height", _get_height),
    ]


def _valobj_from_signed(source: SBValue, val: int, name="") -> SBValue:
    ty: SBType = source.target.GetBasicType(lldb.eBasicTypeInt)
    data = SBData.CreateDataFromInt(val, ty.GetByteSize())
    return source.CreateValueFromData(name, data, ty)
