{
    'name': "Gestion de Parking",
    'summary': "Modulo para gestionar tickets de estacionamiento",
    'description': """
        Este modulo se conecta con un sistema de IA ANPR
        para crear tickets y facturar.
    """,
    'author': "odo-park",
    'category': 'Services/Parking',
    'version': '19.0.1.0.0',
    'depends': ['base', 'account', 'l10n_ar', 'portal', 'l10n_latam_invoice_document'],
    'data': [
        'security/ir.model.access.csv',
        'views/parking_ticket_views.xml',
    ],
    'installable': True,
    'application': True, 
}
