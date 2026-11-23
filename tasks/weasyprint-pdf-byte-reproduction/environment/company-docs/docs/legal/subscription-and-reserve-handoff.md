**Versão: 2026-09-22**

# Subscrição e transferência de reservas

[apoio]: operational-responsibilities.md
[remissao]: #decisao

## Objeto e âmbito

Este documento regula a aceitação da subscrição dos serviços da Estuário Serviços e a passagem dos saldos de reserva para a equipa que acompanha a relação comercial. Aplica-se às contas de clientes empresariais com cobrança mensal e reserva constituída para despesas de execução. A reserva não constitui receita de subscrição nem autoriza, por si só, a contratação de serviços adicionais. O seu titular continua a ser o cliente identificado no acordo de adesão, até à aplicação dos fundos numa [obrigação reconhecida][remissao] ou à sua restituição.

O responsável pela conta deve associar o acordo assinado ao registo de abertura e confirmar a identidade da pessoa que dá instruções. A mera receção de uma transferência não vale como aceitação de todas as condições. Quando o pagamento chega antes da assinatura, o valor fica por identificar, sem disponibilidade para utilização pela operação. A equipa comercial deve explicar esta situação ao cliente sem prometer uma data de ativação que ainda dependa de documentação.[^conferencia]

## Aceitação e início do serviço

1. Conferir a denominação social, o número fiscal e a morada de faturação com os elementos entregues pelo cliente.
2. Confirmar a pessoa autorizada a aprovar despesas e o contacto que recebe os avisos de saldo.
3. Registar a data de início e enviar a confirmação com a discriminação entre subscrição e reserva.

A aceitação fica concluída quando existem uma proposta em vigor, uma assinatura válida e uma confirmação de abertura enviada pelo atendimento. A data de início acordada determina o primeiro período de subscrição. Se o cliente pede o adiamento antes de qualquer trabalho, o atendimento recolhe a nova data por escrito e solicita às finanças a atualização da previsão de cobrança. Um adiantamento relativo à reserva mantém a sua natureza durante esse intervalo.

A referência operacional `aceite_subscricao` identifica a confirmação de abertura. Não deve ser usada para registar uma simples troca de propostas. Se houver divergência entre o acordo e a ficha comercial, prevalece o acordo assinado até que ambas as partes documentem uma alteração. O atendimento mantém a ficha em revisão e não solicita uma cobrança baseada no campo que está em discussão.

## Titularidade e separação dos valores

[^entrega]: O resumo segue acompanhado dos comprovativos que permitem identificar cada parcela, sem reunir documentos alheios à conta. A pessoa recetora confirma os elementos em falta e atribui o seu seguimento, conforme o [procedimento de conferência dos suportes][apoio].

Os montantes de reserva são acompanhados por cliente e por finalidade. Uma conta pode ter uma reserva para diligências documentais e outra para despesas de transporte, desde que essa separação conste do acordo. Não se compensa um saldo negativo de uma finalidade com o saldo positivo de outra sem autorização expressa. A expressão "reserva disponível" respeita apenas à conta identificada. A pessoa que acompanha a conta não pode tratar valores de clientes diferentes como uma disponibilidade comum.

| Situação do valor | Tratamento pela operação | Documento de suporte |
| --- | --- | --- |
| Crédito confirmado pelo banco | Disponível para a finalidade acordada | Comprovativo e identificação da conta |
| Pagamento sem referência suficiente | Pendente de identificação | Pedido de esclarecimento ao remetente |
| Despesa aprovada e ainda não liquidada | Parcela comprometida | Aprovação e estimativa do fornecedor |
| Saldo a restituir | Separado da disponibilidade corrente | Instrução de restituição confirmada |

As finanças registam separadamente o **saldo contabilístico** e a disponibilidade operacional. Uma diferença temporária pode resultar de uma despesa aprovada cujo comprovativo ainda não foi recebido. A passagem de responsabilidade deve mostrar essa diferença, com a sua causa e a pessoa que acompanha a regularização. O [procedimento de reconciliação][apoio] descreve o confronto dos movimentos e a resolução das divergências.[^entrega]

[apoio]: reserve-reconciliation.md

## Constituição e reforço da reserva

- O atendimento explica a finalidade do reforço e recolhe eventuais limites de aprovação.
- As finanças confirmam a entrada efetiva do dinheiro antes de aumentar a disponibilidade.
- A operação avisa quando a falta de fundos pode afetar uma diligência com prazo conhecido.

O valor inicial consta da proposta e deve corresponder à previsão razoável das despesas do primeiro período. Para a conta de Lídia & Vale, por exemplo, a reserva de 740,00 € cobre diligências e entregas, enquanto a mensalidade de 186,50 € remunera o acompanhamento. A descrição do pagamento deve permitir distinguir os dois valores. Um reforço recebido a meio do mês não altera automaticamente o preço nem a duração da subscrição.

O aviso de reforço indica o saldo disponível, as despesas já comprometidas e o valor solicitado. Deve dar ao cliente tempo útil para decidir, atendendo às datas das diligências. Se o reforço não chega, a operação suspende apenas o trabalho que exige nova despesa, salvo acordo diferente. As atividades cobertas pela subscrição continuam enquanto o contrato estiver em vigor e houver condições materiais para as executar.

## Preparação da transferência

A transferência de acompanhamento deve ser preparada com informação suficientemente recente para a equipa recetora assumir a conta sem repetir pedidos já respondidos. O resumo identifica o período reconciliado, as despesas pendentes, os compromissos assumidos e os contactos autorizados. Uma folha de saldo sem esses elementos não substitui a passagem de contexto. Os documentos recebidos no próprio dia podem ser incluídos como pendentes, desde que tenham responsável e data de revisão.

O registo `reserva_transferivel` corresponde à parcela que pode acompanhar a conta. Não inclui valores cuja titularidade esteja por esclarecer, montantes bloqueados por uma objeção fundamentada ou quantias já destinadas a uma restituição aprovada. A equipa que entrega não elimina essas parcelas do histórico: discrimina-as e indica como serão tratadas depois da mudança de responsável.

| Elemento da passagem | Quem prepara | Quem confirma |
| --- | --- | --- |
| Saldo e movimentos desde o último fecho | Finanças | Analista recetor |
| Diligências e compromissos em curso | Operação de origem | Operação recetora |
| Contactos e autorizações do cliente | Atendimento | Gestor da conta |
| Divergências com impacto jurídico | Jurídico | Responsável pela decisão |

A confirmação da equipa recetora deve mencionar as reservas que aceita e as pendências que conhece. Se a passagem ocorrer durante uma ausência, a chefia designa uma pessoa substituta com acesso aos registos necessários. A distribuição de funções consta de [responsabilidades operacionais][apoio], incluindo a forma de escalar uma questão que afete mais de uma equipa.

## Conferência e fecho do saldo

[apoio]: billing-disputes.md

Antes de concluir a passagem, as finanças confrontam os créditos bancários com o razão da reserva e com as despesas aprovadas. O período de corte é comunicado às duas equipas. Um movimento posterior ao corte não pode desaparecer entre relatórios: fica associado à origem até ser incluído na confirmação complementar. A diferença de data entre a autorização de uma despesa e o seu pagamento deve ser visível, sem duplicar o valor comprometido.

Quando a reserva tem moeda diferente da despesa, o resumo apresenta a taxa efetivamente aplicada e o encargo de conversão, se existir. Não se usam taxas indicativas para dar por concluída uma restituição. Uma diferença de cêntimos é identificada e explicada como qualquer outra diferença; o seu reduzido valor não autoriza uma alteração silenciosa. O tratamento de objeções a faturas segue o documento de [contestações de cobrança][apoio].

1. Fixar o último movimento incluído no fecho e guardar os respetivos comprovativos.
2. Separar o saldo livre, o valor comprometido e as parcelas sob análise.
3. Obter a concordância da pessoa que recebe e comunicar o resumo ao atendimento.

[^conferencia]: Uma divergência é confrontada com o documento que sustenta o movimento, seguindo o [procedimento de apreciação dos valores][apoio]. O resumo distingue a parcela confirmada daquela que aguarda esclarecimento.

    O registo conserva o motivo, a pessoa responsável e a comunicação da decisão, segundo as [disposições sobre valores em discussão][remissao], permitindo acompanhar a correção sem perder o fecho recebido.

## Informação ao cliente

O cliente recebe uma comunicação que identifica a equipa que passa a acompanhar a conta, a data da mudança e os canais de contacto. O aviso distingue uma mudança interna de responsável de qualquer alteração das condições comerciais. Se houver uma alteração contratual, esta depende do instrumento adequado e não de uma frase inserida no aviso de passagem. O silêncio do cliente não transforma uma proposta de alteração numa autorização.

As mensagens devem usar os contactos confirmados e respeitar a preferência de canal registada. Se o correio eletrónico devolve erro, o atendimento procura um meio alternativo permitido e conserva o registo da tentativa. Uma chamada pode resolver uma dúvida, mas não substitui o documento necessário para autorizar uma nova aplicação da reserva. Os modelos e os registos de consentimento são tratados em [avisos e consentimentos][apoio].[^conferencia]

> A passagem entre equipas não altera a titularidade dos fundos nem reduz o direito do cliente a receber uma explicação dos movimentos. Qualquer limitação à disponibilidade deve ter uma causa concreta e um responsável identificado.

[apoio]: customer-notice-and-consent.md

## Exceções e valores em discussão {#decisao}

Uma transferência pode avançar com uma pendência delimitada quando a equipa recetora dispõe de informação para a acompanhar e a pendência não impede o serviço acordado. A decisão identifica o valor, a causa, a medida provisória e a pessoa que dá seguimento. Não é suficiente escrever que o assunto será resolvido depois. Se a dúvida respeita à identidade do titular ou à legitimidade de quem dá instruções, a utilização dos fundos fica suspensa.

| Ocorrência | Medida provisória | Decisão necessária |
| --- | --- | --- |
| Comprovativo de despesa por receber | Manter o valor comprometido | Finanças confirma a liquidação |
| Cliente contesta a aplicação de uma parcela | Separar a parcela discutida | Jurídico e finanças apreciam o suporte |
| Pedido de devolução para conta diferente | Aguardar confirmação independente | Finanças verifica titularidade |
| Acordo com duas pessoas autorizadas | Respeitar a forma de autorização pactuada | Atendimento obtém as confirmações |

Uma exceção aprovada tem prazo de revisão e não se renova por inércia. Se chega informação que muda o risco da decisão, o responsável comunica-a às equipas envolvidas no próprio ciclo de acompanhamento. Uma restituição não pode ser acelerada omitindo uma verificação de titularidade, mesmo quando a pessoa que a pede é um contacto habitual.

## Cancelamento e restituição

[apoio]: cancellation-and-final-balance.md

O cancelamento da subscrição e a restituição da reserva são operações relacionadas, mas distintas. O último período de serviço é apurado segundo o acordo; o saldo da reserva é apurado pelos movimentos efetivos. Uma dívida de subscrição não é abatida à reserva sem fundamento contratual e comunicação adequada. O [fecho de subscrição][apoio] orienta a confirmação da data de fim, as despesas ainda em curso e o destino do saldo remanescente.

A restituição aprovada identifica a conta de destino, o titular e o montante. A ordem só é considerada executada depois de confirmada pelo banco. Se o pagamento é rejeitado, as finanças mantêm o saldo em aberto e pedem os elementos necessários para nova tentativa. O atendimento não deve comunicar que o cliente já recebeu o dinheiro com base apenas na criação da ordem interna.

## Continuidade de diligências e autorizações

A mudança de equipa pode ocorrer enquanto há entregas, consultas ou pedidos a terceiros em curso. A operação de origem apresenta cada compromisso com a data prevista e o limite de despesa autorizado. A equipa recetora confirma que consegue contactar a pessoa ou entidade que executa o trabalho. Um nome num resumo não basta quando falta o canal de contacto ou quando a pessoa deixou de acompanhar o assunto.

No caso de uma diligência marcada para o próprio dia da passagem, as equipas combinam quem confirma a execução e quem recebe o comprovativo. O fornecedor recebe uma indicação única sobre o destino dos documentos. Se as duas equipas recebem a mesma fatura, as finanças conferem a referência antes de a aplicar à reserva. O cliente não deve suportar duas cobranças porque o documento circulou por mais de um canal.

As autorizações acompanham o contexto em que foram dadas. Uma aprovação para recolher documentos em Aveiro não abrange uma deslocação adicional a Coimbra sem que o acordo o permita. Se a alteração é necessária para cumprir o objetivo do trabalho, a operação apresenta ao cliente a diferença de prazo e de custo. A decisão de avançar fica associada à autorização inicial, para que o conjunto possa ser compreendido depois da passagem.

Os documentos de execução recebidos por correio devem ser associados à conta antes de seguir para a equipa recetora. Se um original precisa de circular fisicamente, fica identificado quem o recebeu e a quem o entregou. Uma fotografia de trabalho pode ajudar o seguimento, mas não substitui o documento necessário à prestação de contas.

| Compromisso em curso | Informação que acompanha | Ato de continuidade |
| --- | --- | --- |
| Recolha documental agendada | Local, contacto e estimativa aprovada | Confirmar a realização e receber o recibo |
| Entrega dependente de terceiro | Data prevista e condição em falta | Pedir confirmação antes de nova marcação |
| Despesa autorizada com limite | Montante máximo e finalidade | Conferir qualquer acréscimo com o cliente |
| Serviço cancelado pelo fornecedor | Aviso recebido e eventual encargo | Confirmar a libertação do compromisso |
| Reembolso de uma despesa adiantada | Pessoa que pagou e suporte disponível | Conferir a legitimidade e evitar duplicação |
| Pedido sem confirmação de receção | Destinatário e tentativas de contacto | Atribuir o próximo contacto a uma pessoa |

## Registos e proteção da informação {#registos}

O dossiê da passagem inclui o acordo, as confirmações de saldo, as autorizações relevantes e a comunicação ao cliente. O acesso é limitado às pessoas que precisam desses elementos para executar ou supervisionar o serviço. Não se copiam documentos de identificação para uma mensagem coletiva quando basta indicar que a identidade foi conferida. O [procedimento de tratamento e conservação][apoio] define os prazos e as situações que justificam uma suspensão da eliminação.

Os registos operacionais devem permitir perceber quem praticou cada ato sem exigir a circulação de credenciais pessoais. O identificador `fecho_reserva` assinala a conclusão administrativa depois da liquidação das pendências; não apaga os movimentos nem impede uma correção documentada. Uma correção posterior deve preservar o sentido do registo anterior e explicar a razão do ajustamento, em vez de substituir o histórico por um saldo sem origem.

[apoio]: processing-and-retention.md

## Confirmação da passagem

A equipa de origem confirma que os movimentos conhecidos até ao corte foram incluídos ou discriminados como pendentes. A equipa recetora confirma que dispõe dos [elementos para acompanhar a conta][remissao] e sabe a quem dirigir as questões abertas.[^entrega]

---

O atendimento confirma a expedição do aviso e guarda o resultado da entrega. As três confirmações podem ocorrer em momentos distintos, mas a responsabilidade pela conta deve estar atribuída durante todo o intervalo. Se uma confirmação não puder ser obtida, a chefia identifica a limitação e decide a medida de continuidade. A decisão não dispensa a reconciliação nem transfere para o cliente o encargo de recompor registos internos. A conclusão da passagem é comunicada às pessoas envolvidas com indicação da data de efeito e das pendências que continuam em acompanhamento.

[remissao]: #registos

## Notas
