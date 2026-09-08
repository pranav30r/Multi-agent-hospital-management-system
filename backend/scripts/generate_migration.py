import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import Base
import app.models
import networkx as nx
import sqlalchemy as sa

G = nx.DiGraph()
for t_name, table in Base.metadata.tables.items():
    G.add_node(t_name)
    for fk in table.foreign_keys:
        target_t = fk.column.table.name
        if target_t != t_name:
            G.add_edge(target_t, t_name)

creation_order = list(nx.topological_sort(G))

lines = [
    '"""Initial baseline schema migration (35 explicit tables)',
    '',
    'Revision ID: 0001_initial_schema',
    'Revises: ',
    'Create Date: 2026-08-27 19:50:00',
    '',
    '"""',
    'from typing import Sequence, Union',
    'from alembic import op',
    'import sqlalchemy as sa',
    '',
    '# revision identifiers, used by Alembic.',
    'revision: str = "0001_initial_schema"',
    'down_revision: Union[str, None] = None',
    'branch_labels: Union[str, Sequence[str], None] = None',
    'depends_on: Union[str, Sequence[str], None] = None',
    '',
    '',
    'def upgrade() -> None:',
]

def repr_type(t):
    if isinstance(t, sa.String):
        if t.length:
            return f"sa.String(length={t.length})"
        return "sa.String()"
    elif isinstance(t, sa.Integer):
        return "sa.Integer()"
    elif isinstance(t, sa.Float):
        return "sa.Float()"
    elif isinstance(t, sa.Boolean):
        return "sa.Boolean()"
    elif isinstance(t, sa.DateTime):
        return "sa.DateTime()"
    elif isinstance(t, sa.Text):
        return "sa.Text()"
    elif isinstance(t, sa.JSON):
        return "sa.JSON()"
    return f"sa.{type(t).__name__}()"

for t_name in creation_order:
    table = Base.metadata.tables[t_name]
    lines.append(f"    # Table: {t_name}")
    lines.append(f"    op.create_table(")
    lines.append(f"        '{t_name}',")
    for col in table.columns:
        col_type = repr_type(col.type)
        parts = [f"sa.Column('{col.name}', {col_type}"]
        
        # Check foreign keys on this column
        for fk in col.foreign_keys:
            target = f"{fk.column.table.name}.{fk.column.name}"
            parts.append(f"sa.ForeignKey('{target}')")

        if col.primary_key:
            parts.append("primary_key=True")
        if not col.nullable and not col.primary_key:
            parts.append("nullable=False")
        elif col.nullable and not col.primary_key:
            parts.append("nullable=True")
            
        col_def = ", ".join(parts) + "),"
        lines.append(f"        {col_def}")
    lines.append(f"    )")
    lines.append("")

lines.append("")
lines.append("def downgrade() -> None:")
lines.append("    # Drop tables in reverse topological dependency order")
for t_name in reversed(creation_order):
    lines.append(f"    op.drop_table('{t_name}')")

migration_code = "\n".join(lines) + "\n"
target_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "alembic", "versions", "0001_initial_schema.py"))
with open(target_path, "w", encoding="utf-8") as fh:
    fh.write(migration_code)

print(f"Successfully generated explicit migration with {len(creation_order)} tables at {target_path}")
