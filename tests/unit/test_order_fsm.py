"""Property tests for the order state machine (design §10)."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from trader.domain.instrument import InstrumentId
from trader.domain.orders import IllegalTransition, Order, OrderRequest, OrderState
from trader.domain.types import Side

REQ = OrderRequest(client_order_id="AT1", iid=InstrumentId.parse("NSE:EQ:RELIANCE"), side=Side.BUY, qty=100,
                   price=140000)

ops = st.one_of(
    st.tuples(st.just("to"), st.sampled_from(list(OrderState))),
    st.tuples(st.just("fill"), st.integers(min_value=1, max_value=60)),
)


@given(st.lists(ops, max_size=30))
def test_invariants_hold_for_any_event_sequence(seq) -> None:
    o = Order.new(REQ, 0)
    for t, (kind, arg) in enumerate(seq, start=1):
        before = o.state
        try:
            if kind == "to":
                o.transition(arg, t)
            elif o.state.working or o.state is OrderState.SUBMITTED:
                o.apply_fill(arg, 140000, t)
        except (IllegalTransition, ValueError):
            assert o.state is before  # a refused event changes nothing
        assert 0 <= o.filled_qty <= o.qty
        if before.terminal:
            assert o.state is before  # terminal states are final
        if o.state is OrderState.FILLED:
            assert o.filled_qty == o.qty


def test_fill_lifecycle() -> None:
    o = Order.new(REQ, 0)
    o.transition(OrderState.SUBMITTED, 1)
    o.transition(OrderState.ACCEPTED, 2)
    o.apply_fill(40, 140000, 3)
    assert o.state is OrderState.PARTIAL
    o.apply_fill(60, 140100, 4)
    assert o.state is OrderState.FILLED
    assert o.avg_price == (40 * 140000 + 60 * 140100) / 100


def test_terminal_is_final() -> None:
    o = Order.new(REQ, 0)
    o.transition(OrderState.REJECTED, 1)
    try:
        o.transition(OrderState.ACCEPTED, 2)
    except IllegalTransition:
        pass
    assert o.state is OrderState.REJECTED
