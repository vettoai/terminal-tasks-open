import re
import unicodedata
from datetime import date, timedelta

LOCALITIES = {
    'SP': (
        ('3550308', '11', '05422000', 'Rua Teodoro Sampaio', 'Pinheiros'),
        ('3550308', '11', '04023062', 'Rua Domingos de Morais', 'Vila Mariana'),
        ('3550308', '11', '03310000', 'Rua Tuiuti', 'Tatuapé'),
        ('3509502', '19', '13015001', 'Rua Barão de Jaguara', 'Centro'),
        ('3509502', '19', '13025004', 'Rua Maria Monteiro', 'Cambuí'),
        ('3548500', '13', '11060002', 'Avenida Ana Costa', 'Gonzaga'),
        ('3548500', '13', '11015001', 'Rua Amador Bueno', 'Centro'),
        ('3543402', '16', '14015040', 'Rua São Sebastião', 'Centro'),
        ('3543402', '16', '14020010', 'Avenida Nove de Julho', 'Jardim Sumaré'),
        ('3549904', '12', '12245010', 'Avenida Adhemar de Barros', 'Jardim São Dimas'),
        ('3549904', '12', '12210000', 'Rua XV de Novembro', 'Centro'),
        ('3548708', '15', '18010082', 'Rua da Penha', 'Centro'),
    ),
    'MG': (
        ('3106200', '31', '30112021', 'Avenida Afonso Pena', 'Funcionários'),
        ('3106200', '31', '30140071', 'Rua dos Aimorés', 'Lourdes'),
        ('3106200', '31', '30350090', 'Rua Pium-í', 'Sion'),
        ('3170206', '34', '38400070', 'Avenida Afonso Pena', 'Centro'),
        ('3170206', '34', '38400236', 'Rua Olegário Maciel', 'Centro'),
        ('3136702', '32', '36010002', 'Rua Halfeld', 'Centro'),
        ('3136702', '32', '36016011', 'Avenida Rio Branco', 'Alto dos Passos'),
        ('3118601', '31', '32310180', 'Avenida João César de Oliveira', 'Eldorado'),
        ('3118601', '31', '32040010', 'Rua Doutor Cassiano', 'Centro'),
        ('3122306', '37', '35500001', 'Avenida Primeiro de Junho', 'Centro'),
        ('3143302', '38', '39400000', 'Rua Doutor Santos', 'Centro'),
        ('3152501', '35', '37550000', 'Avenida Doutor Lisboa', 'Centro'),
    ),
    'PR': (
        ('4106902', '41', '80010130', 'Rua XV de Novembro', 'Centro'),
        ('4106902', '41', '80420090', 'Rua Coronel Dulcídio', 'Batel'),
        ('4106902', '41', '80030290', 'Rua Augusto Stresser', 'Alto da Glória'),
        ('4113700', '43', '86010010', 'Avenida Paraná', 'Centro'),
        ('4113700', '43', '86050130', 'Avenida Maringá', 'Vitória'),
        ('4115200', '44', '87013000', 'Avenida Brasil', 'Zona 01'),
        ('4115200', '44', '87020000', 'Avenida Colombo', 'Zona 07'),
        ('4104808', '45', '85801000', 'Avenida Brasil', 'Centro'),
        ('4104808', '45', '85805110', 'Rua Paraná', 'Centro'),
        ('4119905', '42', '84010000', 'Rua Balduíno Taques', 'Centro'),
        ('4108304', '45', '85851000', 'Avenida Jorge Schimmelpfeng', 'Centro'),
        ('4125506', '41', '83005010', 'Rua XV de Novembro', 'Centro'),
    ),
}
GIVEN_NAMES = ('Adriana', 'Aline', 'André', 'Bruna', 'Caio', 'Cecília', 'Cláudia',
               'Danilo', 'Débora', 'Felipe', 'Flávia', 'Henrique', 'Isabela',
               'Joana', 'José', 'Letícia', 'Luís', 'Márcia', 'Mauro', 'Mônica',
               'Paula', 'Priscila', 'Ricardo', 'Roberto', 'Simone', 'Tiago')
SURNAMES = ('Amaral', 'Andrade', 'Borges', 'Campos', 'Cavalcanti', 'Cunha',
            'Ferraz', 'Fonseca', 'Garcia', 'Leite', 'Macedo', 'Mendes', 'Moraes',
            'Moreira', 'Moura', 'Peixoto', 'Prado', 'Ramos', 'Rezende', 'Santana',
            'Siqueira', 'Soares', 'Tavares', 'Vasconcelos')


def slug(text):
    ascii_text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()
    return re.sub('[^a-z0-9]+', '', ascii_text.lower())


def add_registrations(accounts, rng, month):
    registrations = {}
    for account in accounts.values():
        holder = (account['holder_doc'], account['uf'])
        if holder not in registrations:
            municipality, area, postal, street, district = rng.choice(LOCALITIES[account['uf']])
            corporate = account['holder_type'] == 'CNPJ'
            contact = (f'{rng.choice(GIVEN_NAMES)} {rng.choice(SURNAMES)} {rng.choice(SURNAMES)}'
                       if corporate else account['holder_name'])
            number = rng.randint(17, 2387)
            complement = rng.choice(('', '', '', 'loja 1', 'sala 12', 'fundos', 'térreo', 'conjunto 23'))
            address = f'{street}, {number}' + (f', {complement}' if complement else '') + f' - {district}'
            if corporate:
                phone = area + str(rng.randint(23000000, 49999999))
                domain = slug(account['holder_name'].removesuffix(' Ltda')) + slug(contact.split()[-1])
                email = f'financeiro@{domain}.com.br'
            else:
                phone = area + '9' + str(rng.randint(10000000, 99999999))
                mailbox = slug(contact.split()[0] + '.' + contact.split()[-1])
                email = f'{mailbox}{rng.randint(11, 9876)}@{rng.choice(("gmail.com", "outlook.com", "uol.com.br", "hotmail.com"))}'
            start = date.fromisoformat(month + '-01') - timedelta(days=rng.randint(90, 2300))
            registrations[holder] = {
                'holder_address': address, 'holder_postal_code': postal,
                'holder_municipality': municipality, 'contact_name': contact,
                'contact_phone': phone, 'contact_email': email,
                'relationship_start': start.strftime('%Y%m%d')}
        account.update(registrations[holder])
