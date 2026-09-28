"""Subject-matter domains used to steer translation terminology."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Domain:
    code: str
    name: str
    instructions: str


DOMAINS: dict[str, Domain] = {
    d.code: d
    for d in [
        Domain(
            code="general",
            name="General",
            instructions="General conversation. Prefer plain, natural wording.",
        ),
        Domain(
            code="business",
            name="Business",
            instructions=(
                "Business meetings and corporate communication. Use standard business "
                "terminology; keep company, product and brand names unchanged."
            ),
        ),
        Domain(
            code="accounting_tax",
            name="Accounting & Tax",
            instructions=(
                "Portuguese accounting and tax context. Use the professional "
                "terminology of Portuguese accountants (contabilistas certificados). "
                "Keep these Portuguese abbreviations and institution names exactly as "
                "they are, never expand, translate or 'correct' them unless a glossary "
                "entry says otherwise: IVA, IRC, IRS, IMI, IMT, IS, AT (Autoridade "
                "Tributária e Aduaneira), SS (Segurança Social), OCC (Ordem dos "
                "Contabilistas Certificados), NIF, NIPC, SAF-T, IES, CAE, TSU. "
                "Recognise and translate precisely: contabilidade organizada, regime "
                "simplificado, fatura, fatura-recibo, recibo verde, recibo, retenção na "
                "fonte, declaração periódica (de IVA), declaração de rendimentos, "
                "Modelo 22, pagamento por conta, pagamento especial por conta, "
                "tributação autónoma, dedução, reembolso, coima, derrama. When "
                "translating into another language, keep the Portuguese abbreviation "
                "itself (e.g. 'IVA' stays 'IVA', not 'VAT' or '增值税')."
            ),
        ),
        Domain(
            code="legal",
            name="Legal",
            instructions=(
                "Legal context. Translate precisely and formally; preserve the legal "
                "meaning over fluency. Keep names of laws, articles (e.g. 'artigo 5.º'), "
                "courts and institutions accurate; do not paraphrase obligations."
            ),
        ),
    ]
}

DEFAULT_DOMAIN = "general"


def get_domain(code: str | None) -> Domain:
    return DOMAINS.get(code or DEFAULT_DOMAIN, DOMAINS[DEFAULT_DOMAIN])
