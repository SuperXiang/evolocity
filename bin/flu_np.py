from mutation import *

np.random.seed(1)
random.seed(1)

def parse_args():
    import argparse
    parser = argparse.ArgumentParser(description='Flu NP sequence analysis')
    parser.add_argument('model_name', type=str,
                        help='Type of language model (e.g., hmm, lstm)')
    parser.add_argument('--namespace', type=str, default='np',
                        help='Model namespace')
    parser.add_argument('--dim', type=int, default=512,
                        help='Embedding dimension')
    parser.add_argument('--batch-size', type=int, default=1000,
                        help='Training minibatch size')
    parser.add_argument('--n-epochs', type=int, default=20,
                        help='Number of training epochs')
    parser.add_argument('--seed', type=int, default=1,
                        help='Random seed')
    parser.add_argument('--checkpoint', type=str, default=None,
                        help='Model checkpoint')
    parser.add_argument('--train', action='store_true',
                        help='Train model')
    parser.add_argument('--train-split', action='store_true',
                        help='Train model on portion of data')
    parser.add_argument('--test', action='store_true',
                        help='Test model')
    parser.add_argument('--embed', action='store_true',
                        help='Analyze embeddings')
    parser.add_argument('--epistasis', action='store_true',
                        help='Analyze epistasis')
    args = parser.parse_args()
    return args

def parse_phenotype(field):
    field = field.split('_')[-1]
    if field == 'No':
        return 'no'
    elif field == 'Yes':
        return 'yes'
    else:
        return 'unknown'

def load_meta(meta_fnames):
    with open('data/influenza/birds.txt') as f:
        birds = set(f.read().lower().rstrip().split())

    metas = {}
    for fname in meta_fnames:
        with open(fname) as f:
            for line in f:
                if not line.startswith('>'):
                    continue
                accession = line[1:].rstrip()
                fields = line.rstrip().split('|')

                subtype = fields[4]
                year = fields[5]
                date = fields[5]
                country = fields[7]
                host = fields[9].lower()
                resist_admantane = parse_phenotype(fields[12])
                resist_oseltamivir = parse_phenotype(fields[13])
                virulence = parse_phenotype(fields[14])
                transmission = parse_phenotype(fields[15])

                if year == '-' or year == 'NA' or year == '':
                    year = None
                else:
                    year = int(year.split('/')[-1])

                if date == '-' or date == 'NA' or date == '':
                    date = None
                else:
                    date = dparse(date)

                if host in birds:
                    hosts = 'avian'

                metas[accession] = {
                    'subtype': subtype,
                    'year': year,
                    'date': date,
                    'country': country,
                    'host': host,
                    'resist_admantane': resist_admantane,
                    'resist_oseltamivir': resist_oseltamivir,
                    'virulence': virulence,
                    'transmission': transmission,
                }

    return metas

def process(args, fnames, meta_fnames):
    metas = load_meta(meta_fnames)

    seqs = {}
    for fname in fnames:
        for record in SeqIO.parse(fname, 'fasta'):
            accession = record.description
            meta = metas[accession]
            meta['seqlen'] = len(str(record.seq))
            if meta['seqlen'] < 450:
                continue
            if 'X' in record.seq:
                continue
            if record.seq not in seqs:
                seqs[record.seq] = []
            seqs[record.seq].append(meta)

    tprint('Found {} unique sequences'.format(len(seqs)))

    return seqs

def split_seqs(seqs, split_method='random'):
    train_seqs, test_seqs = {}, {}

    old_cutoff = 1900
    new_cutoff = 2008

    tprint('Splitting seqs...')
    for seq in seqs:
        # Pick validation set based on date.
        seq_dates = [
            meta['year'] for meta in seqs[seq]
            if meta['year'] is not None
        ]
        if len(seq_dates) == 0:
            test_seqs[seq] = seqs[seq]
            continue
        if len(seq_dates) > 0:
            oldest_date = sorted(seq_dates)[0]
            if oldest_date < old_cutoff or oldest_date >= new_cutoff:
                test_seqs[seq] = seqs[seq]
                continue
        train_seqs[seq] = seqs[seq]
    tprint('{} train seqs, {} test seqs.'
           .format(len(train_seqs), len(test_seqs)))

    return train_seqs, test_seqs

def setup(args):
    fnames = [ 'data/influenza/ird_influenzaA_NP_allspecies.fa' ]
    meta_fnames = fnames

    seqs = process(args, fnames, meta_fnames)

    seq_len = max([ len(seq) for seq in seqs ]) + 2
    vocab_size = len(AAs) + 2

    model = get_model(args, seq_len, vocab_size,
                      inference_batch_size=1000)

    return model, seqs

def interpret_clusters(adata):
    clusters = sorted(set(adata.obs['louvain']))
    for cluster in clusters:
        tprint('Cluster {}'.format(cluster))
        adata_cluster = adata[adata.obs['louvain'] == cluster]
        for var in [ 'year', 'country', 'subtype' ]:
            tprint('\t{}:'.format(var))
            counts = Counter(adata_cluster.obs[var])
            for val, count in counts.most_common():
                tprint('\t\t{}: {}'.format(val, count))
        tprint('')

    cluster2subtype = {}
    for i in range(len(adata)):
        cluster = adata.obs['louvain'][i]
        if cluster not in cluster2subtype:
            cluster2subtype[cluster] = []
        cluster2subtype[cluster].append(adata.obs['subtype'][i])
    largest_pct_subtype = []
    for cluster in cluster2subtype:
        count = Counter(cluster2subtype[cluster]).most_common(1)[0][1]
        pct_subtype = float(count) / len(cluster2subtype[cluster])
        largest_pct_subtype.append(pct_subtype)
        tprint('\tCluster {}, largest subtype % = {}'
               .format(cluster, pct_subtype))
    tprint('Purity, Louvain and subtype: {}'
           .format(np.mean(largest_pct_subtype)))

def plot_umap(adata):
    sc.tl.umap(adata, min_dist=1.)
    sc.pl.umap(adata, color='louvain', save='_np_louvain.png')
    sc.pl.umap(adata, color='subtype', save='_np_subtype.png')
    sc.pl.umap(adata, color='year', save='_np_year.png')
    sc.pl.umap(adata, color='host', save='_np_host.png')
    sc.pl.umap(adata, color='resist_adamantane', save='_np_adamantane.png')
    sc.pl.umap(adata, color='resist_oseltamivir', save='_np_oseltamivir.png')
    sc.pl.umap(adata, color='virulence', save='_np_virulence.png')
    sc.pl.umap(adata, color='transmission', save='_np_transmission.png')

def populate_embedding(args, model, seqs, vocabulary,
                       use_cache=False, namespace=None):
    if namespace is None:
        namespace = args.namespace

    if use_cache:
        mkdir_p('target/{}/embedding'.format(namespace))
        embed_prefix = ('target/{}/embedding/{}_{}'
                        .format(namespace, args.model_name, args.dim))

    sorted_seqs = np.array([ str(s) for s in sorted(seqs.keys()) ])
    batch_size = 3000
    n_batches = math.ceil(len(sorted_seqs) / float(batch_size))
    for batchi in range(n_batches):
        # Identify the batch.
        start = batchi * batch_size
        end = (batchi + 1) * batch_size
        sorted_seqs_batch = sorted_seqs[start:end]
        seqs_batch = { seq: seqs[seq] for seq in sorted_seqs_batch }

        # Load from cache if available.
        if use_cache:
            embed_fname = embed_prefix + '.{}.npy'.format(batchi)
            if os.path.exists(embed_fname):
                X_embed = np.load(embed_fname, allow_pickle=True)
                if X_embed.shape[0] == len(sorted_seqs_batch):
                    for seq_idx, seq in enumerate(sorted_seqs_batch):
                        for meta in seqs[seq]:
                            meta['embedding'] = X_embed[seq_idx]
                    continue

        # Embed the sequences.
        seqs_batch = embed_seqs(args, model, seqs_batch, vocabulary,
                                use_cache=False)
        if use_cache:
            X_embed = []
        for seq in sorted_seqs_batch:
            for meta in seqs[seq]:
                meta['embedding'] = seqs_batch[seq][0]['embedding'].mean(0)
            if use_cache:
                X_embed.append(seqs[seq][0]['embedding'].ravel())
        del seqs_batch

        if use_cache:
            np.save(embed_fname, np.array(X_embed))

    return seqs

def analyze_embedding(args, model, seqs, vocabulary):
    seqs = populate_embedding(args, model, seqs, vocabulary,
                              use_cache=True)

    X, obs = [], {}
    obs['n_seq'] = []
    obs['seq'] = []
    for seq in seqs:
        meta = seqs[seq][0]
        X.append(meta['embedding'])
        for key in meta:
            if key == 'embedding':
                continue
            if key not in obs:
                obs[key] = []
            obs[key].append(Counter([
                meta[key] for meta in seqs[seq]
            ]).most_common(1)[0][0])
        obs['n_seq'].append(len(seqs[seq]))
        obs['seq'].append(str(seq))
    X = np.array(X)

    adata = AnnData(X)
    for key in obs:
        adata.obs[key] = obs[key]
    #adata = adata[
    #    np.logical_or.reduce((
    #        adata.obs['Host Species'] == 'human',
    #        adata.obs['Host Species'] == 'avian',
    #        adata.obs['Host Species'] == 'swine',
    #    ))
    #]

    sc.pp.neighbors(adata, n_neighbors=200, use_rep='X')
    sc.tl.louvain(adata, resolution=1.)

    sc.set_figure_params(dpi_save=500)
    plot_umap(adata)

    interpret_clusters(adata)

def compute_mut_effects(args, vocabulary, model, nodes, steps,
                        min_pos=None, max_pos=None, verbose=False):
    if 'esm' in args.model_name:
        vocabulary = {
            word: model.alphabet_.all_toks.index(word)
            for word in model.alphabet_.all_toks
            if '<' not in word
        }

    steps_set = set(steps)

    mut_effects = []

    for node_idx, (node_name, node) in enumerate(nodes):
        step_effects = {}
        for step_idx, step in enumerate([ 'base' ] + steps):
            if node_idx > 0 and step_idx > 0:
                continue

            if step == 'base':
                seq_pred = node
            else:
                aa_orig = step[0]
                aa_mut = step[-1]
                pos = int(step[1:-1]) - 1
                if node[pos] != aa_orig:
                    continue
                seq_pred = node[:pos] + aa_mut + node[pos+1:]

            y_pred = predict_sequence_prob(
                args, seq_pred, vocabulary, model, verbose=verbose
            )

            if min_pos is None:
                min_pos = 0
            if max_pos is None:
                max_pos = len(seq_pred) - 1

            if step == 'base':
                word_pos_prob = {}

            for i in range(min_pos, max_pos + 1):
                for word in vocabulary:
                    word_idx = vocabulary[word]
                    prob = y_pred[i + 1, word_idx]

                    orig_idx = vocabulary[seq_pred[i]]
                    orig_prob = y_pred[i + 1, orig_idx]

                    if 'esm' in args.model_name:
                        logprob = prob
                        orig_logprob = orig_prob
                        if step == 'base':
                            word_pos_prob[(word, i)] = prob
                    else:
                        logprob = np.log10(prob)
                        orig_logprob = np.log10(orig_prob)
                        if step == 'base':
                            word_pos_prob[(word, i)] = np.log10(prob)

                    ratio_mut = logprob - orig_logprob
                    ratio_back = logprob - word_pos_prob[(word, i)]
                    if seq_pred[i] == word:
                        assert(ratio_mut == 0)

                    mut_name = seq_pred[i] + str(i + 1) + word

                    mut_effects.append([
                        node_idx, node, node_name, step_idx, step,
                        seq_pred[i], word, i, logprob, mut_name,
                        ratio_mut, ratio_back, mut_name in steps_set
                    ])

    mut_effects = pd.DataFrame(mut_effects, columns=[
        'node_idx', 'node', 'node_name', 'step_idx', 'step',
        'orig_word', 'mut_word', 'mut_pos', 'mut_logprob', 'mut_name',
        'ratio_mut', 'ratio_back', 'is_step'
    ])

    return mut_effects

def epi_gong2013(args, model, seqs, vocabulary):
    nodes, steps = [], []
    for record in SeqIO.parse('data/influenza/np_nodes.fa', 'fasta'):
        nodes.append((record.id, str(record.seq)))
        if len(nodes) > 1:
            for idx, (c1, c2) in enumerate(zip(nodes[-2][1], nodes[-1][1])):
                if c1 != c2:
                    steps.append(c1 + str(idx + 1) + c2)

    mut_effects = compute_mut_effects(
        args, vocabulary, model, nodes, steps,
    )

    # Plot single effects of mutants in 1968 strain.

    df = mut_effects[
        (mut_effects.node_idx == 0) & (mut_effects.step_idx == 0) &
        (mut_effects.is_step)
    ]
    plt.figure(figsize=(10, 5),)
    sns.barplot(data=df, x='mut_name', y='mut_logprob')
    plt.xticks(rotation=45)
    plt.savefig('figures/{}_1968_single_logprob.png'.format(args.namespace))
    plt.close()
    plt.figure(figsize=(10, 5))
    sns.barplot(data=df, x='mut_name', y='ratio_mut')
    plt.xticks(rotation=45)
    plt.savefig('figures/{}_1968_single_ratio.png'.format(args.namespace))
    plt.close()


    for node_name, _ in nodes[1:-1]:
       df = mut_effects[
           (mut_effects.node_name == node_name) &
           (mut_effects.step_idx == 0) &
           (mut_effects.is_step)
       ]
       plt.figure(figsize=(10, 5))
       sns.barplot(data=df, x='mut_name', y='ratio_mut')
       plt.xticks(rotation=45)
       plt.savefig('figures/{}_{}_single_ratio.png'
                   .format(args.namespace, node_name))
       plt.close()

    # Plot distribution of effects of mutants in 1968 strain.

    df = mut_effects[
        (mut_effects.node_idx == 0) &
        (mut_effects.orig_word == mut_effects.mut_word)
    ]
    plt.figure(figsize=(10, 5),)
    sns.violinplot(data=df, x='step', y='mut_logprob')
    plt.xticks(rotation=45)
    plt.savefig('figures/{}_1968_dist_logprob.png'.format(args.namespace))
    plt.close()
    plt.figure(figsize=(10, 5))
    sns.violinplot(data=df, x='step', y='ratio_back')
    plt.xticks(rotation=45)
    plt.savefig('figures/{}_1968_dist_ratio.png'.format(args.namespace))
    plt.close()

    # See if N334H rescues L259S.
    df = mut_effects[
        (mut_effects.node_idx == 0) &
        ((mut_effects.step == 'base') | (mut_effects.step == 'N334H')) &
        (mut_effects.mut_name == 'L259S')
    ]
    plt.figure()
    sns.barplot(data=df, x='step', y='mut_logprob')
    plt.xticks(rotation=45)
    plt.savefig('figures/{}_rescue_259S_logprob.png'.format(args.namespace))
    plt.close()
    plt.figure()
    sns.barplot(data=df, x='step', y='ratio_mut')
    plt.xticks(rotation=45)
    plt.savefig('figures/{}_rescue_259S_ratio.png'.format(args.namespace))
    plt.close()

    # Plot how probability of 259S changes across steps.
    df = mut_effects[
        (mut_effects.step_idx == 0) &
        (mut_effects.mut_word == 'S') &
        (mut_effects.mut_pos == 258)
    ]
    plt.figure(figsize=(10, 5),)
    sns.barplot(data=df, x='node_name', y='mut_logprob')
    plt.xticks(rotation=45)
    plt.savefig('figures/{}_time_259S_logprob.png'.format(args.namespace))
    plt.close()
    plt.figure(figsize=(10, 5))
    sns.barplot(data=df, x='node_name', y='ratio_mut')
    plt.xticks(rotation=45)
    plt.savefig('figures/{}_time_259S_ratio.png'.format(args.namespace))
    plt.close()

    # Plot how probability of 384G changes across steps.
    df = mut_effects[
        (mut_effects.step_idx == 0) &
        (mut_effects.mut_word == 'G') &
        (mut_effects.mut_pos == 383)
    ]
    plt.figure(figsize=(10, 5),)
    sns.barplot(data=df, x='node_name', y='mut_logprob')
    plt.xticks(rotation=45)
    plt.savefig('figures/{}_time_384G_logprob.png'.format(args.namespace))
    plt.close()
    plt.figure(figsize=(10, 5))
    sns.barplot(data=df, x='node_name', y='ratio_mut')
    plt.xticks(rotation=45)
    plt.savefig('figures/{}_time_384G_ratio.png'.format(args.namespace))
    plt.close()



if __name__ == '__main__':
    args = parse_args()

    AAs = [
        'A', 'R', 'N', 'D', 'C', 'Q', 'E', 'G', 'H',
        'I', 'L', 'K', 'M', 'F', 'P', 'S', 'T', 'W',
        'Y', 'V', 'X', 'Z', 'J', 'U', 'B',
    ]
    vocabulary = { aa: idx + 1 for idx, aa in enumerate(sorted(AAs)) }

    model, seqs = setup(args)

    if 'esm' in args.model_name:
        args.checkpoint = args.model_name
    elif args.checkpoint is not None:
        model.model_.load_weights(args.checkpoint)
        tprint('Model summary:')
        tprint(model.model_.summary())

    if args.train:
        batch_train(args, model, seqs, vocabulary, batch_size=5000)

    if args.train_split or args.test:
        train_test(args, model, seqs, vocabulary, split_seqs)

    if args.embed:
        if args.checkpoint is None and not args.train:
            raise ValueError('Model must be trained or loaded '
                             'from checkpoint.')
        no_embed = { 'hmm' }
        if args.model_name in no_embed:
            raise ValueError('Embeddings not available for models: {}'
                             .format(', '.join(no_embed)))
        analyze_embedding(args, model, seqs, vocabulary)

    if args.epistasis:
        if args.checkpoint is None and not args.train:
            raise ValueError('Model must be trained or loaded '
                             'from checkpoint.')
        epi_gong2013(args, model, seqs, vocabulary)
